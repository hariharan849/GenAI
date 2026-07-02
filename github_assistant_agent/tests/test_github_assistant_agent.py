import json
from pathlib import Path

import pytest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import github_assistant_agent as agent


class FakeCommit:
    def __init__(self, sha="abc123def4567890"):
        self.sha = sha


class FakeBranch:
    def __init__(self, sha="abc123def4567890"):
        self.commit = FakeCommit(sha)


class FakeTreeItem:
    def __init__(self, path, sha="file-sha", size=100, type_="blob"):
        self.path = path
        self.sha = sha
        self.size = size
        self.type = type_


class FakeTree:
    def __init__(self, items):
        self.tree = items


class FakeContent:
    def __init__(self, text):
        self.decoded_content = text.encode("utf-8")


class FakeRepo:
    default_branch = "main"

    def __init__(self, sha="abc123def4567890"):
        self.sha = sha

    def get_branch(self, branch):
        return FakeBranch(self.sha)

    def get_git_tree(self, branch, recursive=True):
        return FakeTree(
            [
                FakeTreeItem("README.md", size=80),
                FakeTreeItem("src/app.py", size=120),
                FakeTreeItem("node_modules/pkg/index.js", size=100),
                FakeTreeItem("image.png", size=100),
            ]
        )

    def get_contents(self, path, ref):
        contents = {
            "README.md": "# Demo\n\nThis repository explains repo indexing.",
            "src/app.py": "def answer_question():\n    return 'indexed context'\n",
        }
        return FakeContent(contents[path])


def test_normalize_github_repo_variants():
    assert agent.normalize_github_repo("owner/repo") == "owner/repo"
    assert agent.normalize_github_repo("https://github.com/Owner/Repo") == "Owner/Repo"
    assert agent.normalize_github_repo("https://github.com/owner/repo.git") == "owner/repo"
    assert agent.normalize_github_repo("git@github.com:owner/repo.git") == "owner/repo"


@pytest.mark.parametrize("repo", ["", "owner", "https://example.com/owner/repo", "owner/repo/extra"])
def test_normalize_github_repo_rejects_invalid(repo):
    with pytest.raises(agent.InvalidRepositoryError):
        agent.normalize_github_repo(repo)


def test_cache_key_generation():
    assert (
        agent.cache_key_for_repo("Owner/Repo", "abcdef1234567890")
        == "owner__repo__abcdef123456"
    )


def test_ignored_path_filtering():
    assert agent.should_ignore_path("node_modules/react/index.js")
    assert agent.should_ignore_path("dist/app.js")
    assert agent.should_ignore_path("assets/logo.png")
    assert not agent.should_ignore_path("src/github_assistant_agent.py")
    assert not agent.should_ignore_path("README.md")


def test_text_detection_rejects_binary():
    assert agent.is_probably_text("src/app.py", b"print('ok')\n")
    assert not agent.is_probably_text("data.bin", b"\x00\x01")
    assert not agent.is_probably_text("image.png", b"\x89PNG\r\n")


def test_retrieve_chunks_scores_path_and_text():
    summary = agent.RepoIndexSummary(
        repo="owner/repo",
        default_branch="main",
        commit_sha="abc123",
        cache_key="owner__repo__abc123",
        cache_dir="cache",
        files_indexed=1,
        files_skipped=0,
        chunks_indexed=2,
        total_chars=20,
        refreshed=False,
        reused=False,
        created_at="2026-01-01T00:00:00+00:00",
    )
    index = agent.RepoIndex(
        summary=summary,
        chunks=[
            agent.RepoIndexChunk(
                repo="owner/repo",
                commit_sha="abc123",
                path="README.md",
                language="Markdown",
                text="installation notes",
                start_line=1,
                end_line=1,
                source_url="https://example.com/readme",
            ),
            agent.RepoIndexChunk(
                repo="owner/repo",
                commit_sha="abc123",
                path="src/auth.py",
                language="Python",
                text="token validation",
                start_line=1,
                end_line=1,
                source_url="https://example.com/auth",
            ),
        ],
    )

    results = agent.retrieve_chunks(index, "how does auth token validation work")

    assert [chunk.path for chunk in results] == ["src/auth.py"]


def test_index_repository_stores_chunks_with_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "_resolve_repo", lambda github_repo, token: FakeRepo())
    monkeypatch.setattr(agent, "settings", agent.Settings(github_assistant_cache_dir=tmp_path))

    summary = agent.index_repository("owner/repo", gh_token="token")

    assert summary.repo == "owner/repo"
    assert summary.files_indexed == 2
    assert summary.chunks_indexed == 2
    index_path = Path(summary.cache_dir) / "index.json"
    assert index_path.exists()
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    assert payload["chunks"][0]["source_url"].startswith(
        "https://github.com/owner/repo/blob/abc123def4567890/"
    )


def test_index_repository_reuses_matching_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "_resolve_repo", lambda github_repo, token: FakeRepo())
    monkeypatch.setattr(agent, "settings", agent.Settings(github_assistant_cache_dir=tmp_path))

    first = agent.index_repository("owner/repo", gh_token="token")
    second = agent.index_repository("owner/repo", gh_token="token")

    assert first.reused is False
    assert second.reused is True
    assert second.commit_sha == first.commit_sha


def test_is_index_stale(monkeypatch):
    monkeypatch.setattr(agent, "_resolve_repo", lambda github_repo, token: FakeRepo("newsha"))

    assert agent.is_index_stale("owner/repo", "oldsha", gh_token="token") is True
    assert agent.is_index_stale("owner/repo", "newsha", gh_token="token") is False


def test_missing_token_error(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(agent.MissingTokenError):
        agent.resolve_github_token(None)


def test_cli_index_dispatch(monkeypatch, capsys):
    called = {}

    def fake_index(repo, token, refresh=False):
        called["args"] = (repo, token, refresh)
        return agent.RepoIndexSummary(
            repo="owner/repo",
            default_branch="main",
            commit_sha="abc123def456",
            cache_key="owner__repo__abc123def456",
            cache_dir="cache",
            files_indexed=1,
            files_skipped=0,
            chunks_indexed=1,
            total_chars=10,
            refreshed=refresh,
            reused=False,
            created_at="2026-01-01T00:00:00+00:00",
        )

    monkeypatch.setattr(agent, "index_repository", fake_index)

    assert agent.main(["--index", "--repo", "owner/repo", "--token", "t"]) == 0
    assert called["args"] == ("owner/repo", "t", False)
    assert "Indexed owner/repo@abc123def456" in capsys.readouterr().out


def test_cli_qna_dispatch(monkeypatch, capsys):
    monkeypatch.setattr(agent, "kickoff", lambda query, github_repo, gh_token: "answer")

    assert agent.main(["How?", "--repo", "owner/repo", "--token", "t"]) == 0
    assert "answer" in capsys.readouterr().out
