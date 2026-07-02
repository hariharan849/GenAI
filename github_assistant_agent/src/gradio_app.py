"""Gradio UI for the repo-aware GitHub Assistant."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import gradio as gr

from github_assistant_agent import GitHubAssistantError, index_repository, kickoff

DESCRIPTION = """
## GitHub Assistant Agent
Index a repository, then ask questions against the cached repository context.
If no local context is available, the assistant can still fall back to live GitHub search.
"""


def run_index(repo: str, token: str, refresh: bool) -> str:
    if not repo.strip():
        return "**Error:** Please enter a repository to index."

    try:
        summary = index_repository(
            github_repo=repo.strip(),
            gh_token=token.strip() or None,
            refresh=refresh,
        )
        reused = "reused existing index" if summary.reused else "created index"
        return (
            f"**Success:** {reused} for `{summary.repo}` at "
            f"`{summary.commit_sha[:12]}`.\n\n"
            f"- Files indexed: {summary.files_indexed}\n"
            f"- Files skipped: {summary.files_skipped}\n"
            f"- Chunks indexed: {summary.chunks_indexed}\n"
            f"- Cache: `{summary.cache_dir}`"
        )
    except GitHubAssistantError as exc:
        return f"**Indexing error:** {exc}"
    except Exception as exc:
        return f"**Unexpected indexing error:** {exc}"


def run_agent(query: str, repo: str, token: str) -> str:
    if not query.strip():
        return "**Error:** Please enter a question."

    try:
        answer = kickoff(
            query=query.strip(),
            github_repo=repo.strip() or None,
            gh_token=token.strip() or None,
        )
        return answer or "_The agent returned an empty result._"
    except ValueError as exc:
        return f"**Input error:** {exc}"
    except Exception as exc:
        return f"**Agent error:** {exc}"


with gr.Blocks(title="GitHub Assistant Agent") as demo:
    gr.Markdown(DESCRIPTION)

    with gr.Row():
        repo_box = gr.Textbox(
            label="GitHub Repo",
            placeholder="owner/repo or https://github.com/owner/repo",
            scale=3,
        )
        token_box = gr.Textbox(
            label="GitHub Token (optional, overrides env var)",
            placeholder="ghp_...",
            type="password",
            scale=2,
        )

    with gr.Row():
        refresh_box = gr.Checkbox(label="Refresh index", value=False)
        index_btn = gr.Button("Index repository", variant="secondary")

    index_status = gr.Markdown(label="Indexing status")

    query_box = gr.Textbox(
        label="Question",
        placeholder="e.g. How is repository state modeled?",
        lines=3,
    )
    ask_btn = gr.Button("Ask", variant="primary")
    output = gr.Markdown(label="Answer")

    index_btn.click(
        fn=run_index,
        inputs=[repo_box, token_box, refresh_box],
        outputs=index_status,
    )
    ask_btn.click(
        fn=run_agent,
        inputs=[query_box, repo_box, token_box],
        outputs=output,
    )
    query_box.submit(
        fn=run_agent,
        inputs=[query_box, repo_box, token_box],
        outputs=output,
    )


if __name__ == "__main__":
    demo.launch()
