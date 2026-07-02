"""Repo-aware GitHub assistant powered by CrewAI and a local repository index."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Optional

from dotenv import load_dotenv
from github import Github, GithubException, RateLimitExceededException, UnknownObjectException
from loguru import logger
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from crewai import LLM, Agent, Crew, Process, Task
from crewai.flow.flow import Flow, listen, start
from crewai_tools import GithubSearchTool

load_dotenv()


IGNORED_DIRS = {
    ".git",
    ".github/workflows",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    ".turbo",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    "coverage",
}

IGNORED_EXTENSIONS = {
    ".7z",
    ".avif",
    ".bin",
    ".bmp",
    ".bz2",
    ".class",
    ".dll",
    ".dylib",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".lock",
    ".mp3",
    ".mp4",
    ".o",
    ".pdf",
    ".png",
    ".pyc",
    ".rar",
    ".so",
    ".svg",
    ".tar",
    ".webp",
    ".woff",
    ".woff2",
    ".zip",
}

IMPORTANT_FILENAMES = {
    "readme",
    "readme.md",
    "readme.rst",
    "license",
    "license.md",
    "contributing.md",
    "code_of_conduct.md",
    "pyproject.toml",
    "package.json",
    "requirements.txt",
    "dockerfile",
    "docker-compose.yml",
}


class GitHubAssistantError(RuntimeError):
    """Base error for user-facing assistant failures."""


class MissingTokenError(GitHubAssistantError):
    """Raised when GitHub access is requested without a token."""


class InvalidRepositoryError(GitHubAssistantError):
    """Raised when a repository reference cannot be normalized or resolved."""


class RepoTooLargeError(GitHubAssistantError):
    """Raised when configured indexing limits are exceeded."""


class NoIndexFoundError(GitHubAssistantError):
    """Raised when a repo-aware answer requires an index that does not exist."""


class GroqSettings(BaseModel):
    api_key: str = Field(default="", description="Groq API key")
    model: str = Field(default="llama-3.3-70b-versatile")
    temperature: float = Field(default=0.2)
    max_tokens: int = Field(default=1000)


class Settings(BaseSettings):
    groq: GroqSettings = Field(default_factory=GroqSettings)
    github_assistant_cache_dir: Path = Field(
        default_factory=lambda: Path(".github_assistant_cache"),
        description="Directory used for repository snapshots and indexes.",
    )
    github_assistant_max_files: int = 250
    github_assistant_max_file_bytes: int = 250_000
    github_assistant_max_total_chars: int = 2_000_000

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=[
            str(Path(__file__).resolve().parents[1] / ".env"),
            str(Path(__file__).resolve().parent / ".env"),
        ],
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
        case_sensitive=False,
        frozen=True,
    )


settings = Settings()


class RepoIndexChunk(BaseModel):
    repo: str
    commit_sha: str
    path: str
    language: str
    text: str
    start_line: int
    end_line: int
    source_url: str


class RepoIndexSummary(BaseModel):
    repo: str
    default_branch: str
    commit_sha: str
    cache_key: str
    cache_dir: str
    files_indexed: int
    files_skipped: int
    chunks_indexed: int
    total_chars: int
    refreshed: bool
    reused: bool
    created_at: str


class RepoIndex(BaseModel):
    summary: RepoIndexSummary
    chunks: list[RepoIndexChunk]


class GitHubAssistantState(BaseModel):
    query: str = ""
    github_repo: Optional[str] = None
    gh_token: str = ""
    retrieved_chunks: list[RepoIndexChunk] = Field(default_factory=list)
    index_summary: Optional[RepoIndexSummary] = None
    index_stale: bool = False
    crew_result: str = ""
    summary: str = ""
    error: str = ""


@dataclass(frozen=True)
class GitHubFile:
    path: str
    sha: str
    size: int


def get_groq_client() -> LLM:
    return LLM(
        model=f"groq/{settings.groq.model}",
        api_key=settings.groq.api_key,
        temperature=settings.groq.temperature,
        max_tokens=settings.groq.max_tokens,
    )


def resolve_github_token(gh_token: Optional[str] = None) -> str:
    token = (gh_token or "").strip() or os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        raise MissingTokenError(
            "A GitHub token is required. Set GITHUB_TOKEN or pass a token explicitly."
        )
    return token


def normalize_github_repo(repo: str) -> str:
    """Normalize a GitHub repo reference to owner/repo format."""
    candidate = repo.strip()
    if not candidate:
        raise InvalidRepositoryError("GitHub repository must be a non-empty string.")

    url_patterns = [
        r"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/?(?:[#?].*)?$",
        r"^git@github\.com:(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?$",
    ]
    for pattern in url_patterns:
        match = re.match(pattern, candidate, re.IGNORECASE)
        if match:
            return f"{match.group('owner')}/{match.group('repo')}"

    if candidate.count("/") == 1:
        owner, repo_name = candidate.split("/")
        if owner.strip() and repo_name.strip() and " " not in candidate:
            return f"{owner.strip()}/{repo_name.strip().removesuffix('.git')}"

    raise InvalidRepositoryError(
        "Invalid GitHub repository format. Use owner/repo or a GitHub repo URL."
    )


def cache_key_for_repo(repo: str, commit_sha: str) -> str:
    normalized = normalize_github_repo(repo).lower().replace("/", "__")
    short_sha = commit_sha[:12]
    return f"{normalized}__{short_sha}"


def repo_cache_root(cache_dir: Optional[Path] = None) -> Path:
    return Path(cache_dir or settings.github_assistant_cache_dir).expanduser().resolve()


def current_index_pointer_path(repo: str, cache_dir: Optional[Path] = None) -> Path:
    owner, name = normalize_github_repo(repo).lower().split("/")
    return repo_cache_root(cache_dir) / "repos" / owner / name / "current.json"


def index_dir_for_key(cache_key: str, cache_dir: Optional[Path] = None) -> Path:
    return repo_cache_root(cache_dir) / "indexes" / cache_key


def should_ignore_path(path: str) -> bool:
    normalized = path.replace("\\", "/").strip("/")
    lower = normalized.lower()
    parts = lower.split("/")
    if any(part in IGNORED_DIRS for part in parts):
        return True
    if any(lower == ignored or lower.startswith(f"{ignored}/") for ignored in IGNORED_DIRS):
        return True
    suffix = Path(lower).suffix
    return suffix in IGNORED_EXTENSIONS


def is_probably_text(path: str, sample: bytes) -> bool:
    if b"\x00" in sample:
        return False
    mime_type, _ = mimetypes.guess_type(path)
    if mime_type and not (
        mime_type.startswith("text/")
        or mime_type in {"application/json", "application/xml", "application/x-yaml"}
    ):
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def path_language(path: str) -> str:
    suffix = Path(path).suffix.lower()
    mapping = {
        ".md": "Markdown",
        ".rst": "reStructuredText",
        ".py": "Python",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".json": "JSON",
        ".toml": "TOML",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".html": "HTML",
        ".css": "CSS",
        ".go": "Go",
        ".rs": "Rust",
        ".java": "Java",
        ".kt": "Kotlin",
        ".sh": "Shell",
        ".sql": "SQL",
    }
    return mapping.get(suffix, suffix.removeprefix(".").upper() or "Text")


def file_priority(file: GitHubFile) -> tuple[int, int, str]:
    name = Path(file.path).name.lower()
    depth = file.path.count("/")
    important = 0 if name in IMPORTANT_FILENAMES or file.path.lower().startswith("docs/") else 1
    return (important, depth, file.path)


def chunk_text(
    text: str,
    *,
    repo: str,
    commit_sha: str,
    path: str,
    source_url: str,
    language: str,
    max_chars: int = 4_000,
    overlap_lines: int = 8,
) -> list[RepoIndexChunk]:
    lines = text.splitlines()
    if not lines:
        return []

    chunks: list[RepoIndexChunk] = []
    start = 0
    while start < len(lines):
        current: list[str] = []
        end = start
        current_chars = 0
        while end < len(lines):
            line = lines[end]
            projected = current_chars + len(line) + 1
            if current and projected > max_chars:
                break
            current.append(line)
            current_chars = projected
            end += 1

        chunk_body = "\n".join(current).strip()
        if chunk_body:
            chunks.append(
                RepoIndexChunk(
                    repo=repo,
                    commit_sha=commit_sha,
                    path=path,
                    language=language,
                    text=chunk_body,
                    start_line=start + 1,
                    end_line=end,
                    source_url=source_url,
                )
            )

        if end >= len(lines):
            break
        start = max(end - overlap_lines, start + 1)

    return chunks


def _github_client(token: str) -> Github:
    return Github(token, per_page=100)


def _resolve_repo(github_repo: str, token: str) -> Any:
    normalized = normalize_github_repo(github_repo)
    try:
        return _github_client(token).get_repo(normalized)
    except UnknownObjectException as exc:
        raise InvalidRepositoryError(
            f"Repository '{normalized}' was not found or the token cannot access it."
        ) from exc
    except RateLimitExceededException as exc:
        raise GitHubAssistantError("GitHub API rate limit exceeded. Retry later.") from exc
    except GithubException as exc:
        raise GitHubAssistantError(f"GitHub API error while resolving repo: {exc.data}") from exc


def _repo_files(repo_obj: Any, branch: str) -> list[GitHubFile]:
    try:
        tree = repo_obj.get_git_tree(branch, recursive=True)
    except GithubException:
        tree = repo_obj.get_git_tree(repo_obj.get_branch(branch).commit.sha, recursive=True)

    files: list[GitHubFile] = []
    for item in tree.tree:
        if item.type == "blob":
            files.append(GitHubFile(path=item.path, sha=item.sha, size=item.size or 0))
    return files


def _read_cached_index(pointer_path: Path) -> Optional[RepoIndex]:
    if not pointer_path.exists():
        return None
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        index_path = Path(pointer["index_path"]) / "index.json"
        if not index_path.exists():
            return None
        return RepoIndex.model_validate_json(index_path.read_text(encoding="utf-8"))
    except (OSError, KeyError, json.JSONDecodeError, ValueError) as exc:
        logger.warning(f"Ignoring unreadable index pointer {pointer_path}: {exc}")
        return None


def load_current_index(github_repo: str, cache_dir: Optional[Path] = None) -> Optional[RepoIndex]:
    return _read_cached_index(current_index_pointer_path(github_repo, cache_dir))


def index_repository(
    github_repo: str,
    gh_token: Optional[str] = None,
    refresh: bool = False,
) -> RepoIndexSummary:
    """Build or reuse a persistent local index for a GitHub repository."""
    token = resolve_github_token(gh_token)
    normalized_repo = normalize_github_repo(github_repo)
    repo_obj = _resolve_repo(normalized_repo, token)
    default_branch = repo_obj.default_branch
    head_sha = repo_obj.get_branch(default_branch).commit.sha
    cache_key = cache_key_for_repo(normalized_repo, head_sha)
    index_dir = index_dir_for_key(cache_key)
    pointer_path = current_index_pointer_path(normalized_repo)
    existing = load_current_index(normalized_repo)

    if (
        existing
        and existing.summary.commit_sha == head_sha
        and Path(existing.summary.cache_dir).exists()
        and not refresh
    ):
        logger.info(f"Repo index cache hit: {normalized_repo}@{head_sha[:12]}")
        return existing.summary.model_copy(update={"reused": True, "refreshed": False})

    if refresh and pointer_path.exists():
        logger.info(f"Refreshing repo index: {normalized_repo}")

    logger.info(f"Resolving repository tree: {normalized_repo}@{default_branch}")
    files = sorted(
        (file for file in _repo_files(repo_obj, default_branch) if not should_ignore_path(file.path)),
        key=file_priority,
    )

    selected_files = [
        file for file in files if 0 < file.size <= settings.github_assistant_max_file_bytes
    ][: settings.github_assistant_max_files]

    if not selected_files:
        raise RepoTooLargeError("No indexable text files were found within the configured limits.")

    chunks: list[RepoIndexChunk] = []
    files_indexed = 0
    skipped = len(files) - len(selected_files)
    total_chars = 0

    for file in selected_files:
        if total_chars >= settings.github_assistant_max_total_chars:
            skipped += 1
            continue

        try:
            content_file = repo_obj.get_contents(file.path, ref=head_sha)
            raw = content_file.decoded_content
        except GithubException as exc:
            logger.warning(f"Skipping {file.path}: GitHub read failed: {exc}")
            skipped += 1
            continue

        if not is_probably_text(file.path, raw[:4096]):
            skipped += 1
            continue

        text = raw.decode("utf-8", errors="replace")
        if not text.strip():
            skipped += 1
            continue

        remaining_chars = settings.github_assistant_max_total_chars - total_chars
        if len(text) > remaining_chars:
            text = text[:remaining_chars]

        source_url = (
            f"https://github.com/{normalized_repo}/blob/{head_sha}/{file.path}"
        )
        file_chunks = chunk_text(
            text,
            repo=normalized_repo,
            commit_sha=head_sha,
            path=file.path,
            source_url=source_url,
            language=path_language(file.path),
        )
        chunks.extend(file_chunks)
        total_chars += len(text)
        files_indexed += 1

    if not chunks:
        raise RepoTooLargeError("Repository contained no readable text chunks to index.")

    summary = RepoIndexSummary(
        repo=normalized_repo,
        default_branch=default_branch,
        commit_sha=head_sha,
        cache_key=cache_key,
        cache_dir=str(index_dir),
        files_indexed=files_indexed,
        files_skipped=skipped,
        chunks_indexed=len(chunks),
        total_chars=total_chars,
        refreshed=refresh,
        reused=False,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    index = RepoIndex(summary=summary, chunks=chunks)

    if refresh and index_dir.exists():
        shutil.rmtree(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    (index_dir / "index.json").write_text(
        index.model_dump_json(indent=2), encoding="utf-8"
    )
    pointer_path.write_text(
        json.dumps({"index_path": str(index_dir), "commit_sha": head_sha}, indent=2),
        encoding="utf-8",
    )
    logger.info(
        f"Indexed {files_indexed} files into {len(chunks)} chunks for {normalized_repo}@{head_sha[:12]}"
    )
    return summary


def tokenise(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_./-]{2,}", text.lower())


def retrieve_chunks(index: RepoIndex, query: str, limit: int = 6) -> list[RepoIndexChunk]:
    query_terms = tokenise(query)
    if not query_terms:
        return []
    query_counter = Counter(query_terms)
    scored: list[tuple[float, RepoIndexChunk]] = []

    for chunk in index.chunks:
        haystack = f"{chunk.path}\n{chunk.language}\n{chunk.text}".lower()
        score = 0.0
        for term, weight in query_counter.items():
            if term in haystack:
                score += weight * (3.0 if term in chunk.path.lower() else 1.0)
        if score:
            scored.append((score, chunk))

    scored.sort(key=lambda item: (-item[0], item[1].path, item[1].start_line))
    return [chunk for _, chunk in scored[:limit]]


def is_index_stale(github_repo: str, indexed_sha: str, gh_token: Optional[str] = None) -> bool:
    token = resolve_github_token(gh_token)
    repo_obj = _resolve_repo(github_repo, token)
    head_sha = repo_obj.get_branch(repo_obj.default_branch).commit.sha
    return head_sha != indexed_sha


def _format_retrieved_context(chunks: list[RepoIndexChunk]) -> str:
    blocks = []
    for idx, chunk in enumerate(chunks, start=1):
        blocks.append(
            "\n".join(
                [
                    f"[{idx}] {chunk.path}:{chunk.start_line}-{chunk.end_line}",
                    f"Language: {chunk.language}",
                    f"Source: {chunk.source_url}#L{chunk.start_line}-L{chunk.end_line}",
                    "```",
                    chunk.text[:4_500],
                    "```",
                ]
            )
        )
    return "\n\n".join(blocks)


def _run_context_agent(query: str, repo: str, chunks: list[RepoIndexChunk], stale: bool) -> str:
    context = _format_retrieved_context(chunks)
    agent = Agent(
        role="Repository Understanding Specialist",
        goal="Answer repository questions using only the provided indexed context.",
        backstory=(
            "You are a careful software researcher. You cite source files, avoid "
            "inventing facts, and clearly state when the retrieved repository "
            "context is insufficient."
        ),
        llm=get_groq_client(),
        tools=[],
        verbose=True,
        max_iter=2,
        allow_delegation=False,
    )
    task = Task(
        description=(
            f"Repository: {repo}\n"
            f"Index status: {'stale against current default branch' if stale else 'current cached index'}\n\n"
            f"Question: {query}\n\n"
            "Use the retrieved repository context below to answer. Cite file paths "
            "and source links. If the context is not enough, say exactly what is "
            "missing instead of guessing.\n\n"
            f"{context}"
        ),
        expected_output=(
            "A structured answer with: Direct answer, Relevant files, Reasoning "
            "summary, Source links, and Limitations."
        ),
        agent=agent,
    )
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True)
    return str(crew.kickoff())


def _run_live_search(query: str, gh_token: str, github_repo: Optional[str]) -> str:
    tool_kwargs: dict[str, Any] = {
        "gh_token": gh_token,
        "config": {
            "embedder": {
                "provider": "fastembed",
                "config": {"model": "BAAI/bge-small-en-v1.5"},
            }
        },
    }
    if github_repo:
        tool_kwargs["github_repo"] = github_repo

    github_tool = GithubSearchTool(**tool_kwargs)
    react_agent = Agent(
        role="GitHub Research Specialist",
        goal=(
            "Answer the user's GitHub-related question accurately by searching "
            "GitHub repositories, code, issues, and pull requests."
        ),
        backstory=(
            "You are an expert software researcher with deep knowledge of the "
            "GitHub ecosystem."
        ),
        llm=get_groq_client(),
        tools=[github_tool],
        verbose=True,
        max_iter=5,
        max_rpm=10,
        allow_delegation=False,
    )
    repo_scope_text = (
        f"Repository scope: {github_repo}\n\n"
        if github_repo
        else "Repository scope: none (global search)\n\n"
    )
    research_task = Task(
        description=(
            "Use the GithubSearchTool to answer the following question.\n\n"
            f"{repo_scope_text}"
            f"Question: {query}\n\n"
            "Provide a structured final answer with source links."
        ),
        expected_output=(
            "A detailed answer containing key findings, relevant links, snippets "
            "where helpful, and a concise summary."
        ),
        agent=react_agent,
    )
    crew = Crew(agents=[react_agent], tasks=[research_task], process=Process.sequential, verbose=True)
    return str(crew.kickoff())


class GitHubAssistantFlow(Flow[GitHubAssistantState]):
    """CrewAI flow that answers from a local repo index before live search."""

    @start()
    def initialize(self) -> str:
        logger.info("=== GitHubAssistantFlow: initialize ===")
        if not self.state.query.strip():
            self.state.error = "No query provided - nothing to answer."
            return "error"

        try:
            self.state.gh_token = resolve_github_token(self.state.gh_token)
            if self.state.github_repo:
                self.state.github_repo = normalize_github_repo(self.state.github_repo)
        except GitHubAssistantError as exc:
            self.state.error = str(exc)
            return "error"
        return "initialized"

    @listen(initialize)
    def search(self, event: str) -> str:
        if event == "error":
            return "error"

        try:
            if self.state.github_repo:
                index = load_current_index(self.state.github_repo)
                if index:
                    self.state.index_summary = index.summary
                    self.state.index_stale = is_index_stale(
                        self.state.github_repo,
                        index.summary.commit_sha,
                        self.state.gh_token,
                    )
                    self.state.retrieved_chunks = retrieve_chunks(index, self.state.query)
                    logger.info(
                        f"Retrieved {len(self.state.retrieved_chunks)} chunks from local index"
                    )
                    if self.state.retrieved_chunks:
                        self.state.crew_result = _run_context_agent(
                            self.state.query,
                            self.state.github_repo,
                            self.state.retrieved_chunks,
                            self.state.index_stale,
                        )
                        return "done"

                logger.info("No useful local context found; falling back to live GitHub search.")

            self.state.crew_result = _run_live_search(
                self.state.query, self.state.gh_token, self.state.github_repo
            )
            return "done"
        except RateLimitExceededException:
            self.state.error = "GitHub API rate limit exceeded. Wait and retry."
            return "error"
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "403" in msg or "rate limit" in msg.lower():
                self.state.error = "GitHub API rate limit exceeded. Wait and retry."
            else:
                self.state.error = f"Assistant execution failed: {exc}"
            logger.exception(self.state.error)
            return "error"

    @listen(search)
    def summarise(self, event: str) -> None:
        if event == "error":
            self.state.summary = f"[ERROR] {self.state.error}"
            return

        raw = self.state.crew_result.strip()
        if not raw:
            self.state.summary = "The agent returned an empty result."
            return

        header_parts = []
        if self.state.index_summary:
            status = "stale" if self.state.index_stale else "current"
            header_parts.append(
                f"Local index: {self.state.index_summary.repo}@{self.state.index_summary.commit_sha[:12]} ({status})"
            )
        if self.state.retrieved_chunks:
            header_parts.append(f"Retrieved chunks: {len(self.state.retrieved_chunks)}")

        header = "\n".join(header_parts)
        self.state.summary = f"{header}\n\n{raw}" if header else raw
        max_chars = 8_000
        if len(self.state.summary) > max_chars:
            self.state.summary = self.state.summary[:max_chars] + "\n\n... [output truncated]"


def kickoff(
    query: str,
    github_repo: Optional[str] = None,
    gh_token: Optional[str] = None,
) -> str:
    """Run the assistant and return the final answer."""
    flow = GitHubAssistantFlow()
    flow.state.query = query
    if github_repo:
        flow.state.github_repo = normalize_github_repo(github_repo)
    if gh_token:
        flow.state.gh_token = gh_token
    flow.kickoff()
    return flow.state.summary


def plot() -> None:
    """Render a Mermaid diagram of the flow."""
    flow = GitHubAssistantFlow()
    flow.plot("github_assistant_flow")
    logger.info("Flow diagram saved to github_assistant_flow.html")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repo-aware GitHub Assistant")
    parser.add_argument("query", nargs="?", help="Question to answer")
    parser.add_argument("--repo", default=None, metavar="OWNER/REPO|URL")
    parser.add_argument("--token", default=None, metavar="GITHUB_PAT")
    parser.add_argument("--index", action="store_true", help="Index the repository and exit")
    parser.add_argument("--refresh", action="store_true", help="Refresh the repository index")
    parser.add_argument("--plot", action="store_true", help="Render the flow diagram and exit")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.plot:
            plot()
            return 0

        if args.index or args.refresh:
            if not args.repo:
                parser.error("--repo is required with --index or --refresh")
            summary = index_repository(args.repo, args.token, refresh=args.refresh)
            print(
                f"Indexed {summary.repo}@{summary.commit_sha[:12]}: "
                f"{summary.files_indexed} files, {summary.chunks_indexed} chunks, "
                f"cache={summary.cache_dir}"
            )
            return 0

        if not args.query:
            parser.error("query is required unless --index, --refresh, or --plot is used")
        answer = kickoff(query=args.query, github_repo=args.repo, gh_token=args.token)
        print("\n" + "=" * 60)
        print("ANSWER")
        print("=" * 60)
        print(answer)
        return 0
    except GitHubAssistantError as exc:
        print(f"Error: {exc}")
        return 2
    except ValueError as exc:
        print(f"Input error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
