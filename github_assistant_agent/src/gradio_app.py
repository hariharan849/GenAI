"""Gradio UI for the GitHub Assistant Agent."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import gradio as gr
from github_assistant_agent import kickoff

DESCRIPTION = """
## GitHub Assistant Agent
Ask any question about GitHub repositories, issues, pull requests, or code.
The agent uses a CrewAI ReAct loop powered by Groq to search GitHub and synthesise an answer.
"""


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
        with gr.Column(scale=3):
            query_box = gr.Textbox(
                label="Query *",
                placeholder="e.g. How does crewai handle tool calling?",
                lines=3,
            )
        with gr.Column(scale=2):
            repo_box = gr.Textbox(
                label="GitHub Repo (optional)",
                placeholder="owner/repo  or  https://github.com/owner/repo",
            )
            token_box = gr.Textbox(
                label="GitHub Token (optional — overrides env var)",
                placeholder="ghp_...",
                type="password",
            )

    search_btn = gr.Button("Search GitHub", variant="primary")
    output = gr.Markdown(label="Result")

    search_btn.click(
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
