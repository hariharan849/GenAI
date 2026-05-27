"""
GitHub Assistant Agent — CrewAI ReAct agent powered by GithubSearchTool.

Flow stages
───────────
1. initialize  – validate config & resolve the GitHub token
2. search      – run the Crew (ReAct loop) against the user query
3. summarise   – post-process / log the final answer
"""

from __future__ import annotations

import os
import re
from typing import Optional
from dotenv import load_dotenv
from typing import ClassVar
from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from crewai import LLM, Agent, Crew, Process, Task
from crewai.flow.flow import Flow, listen, start
from crewai_tools import GithubSearchTool
from loguru import logger
from pydantic import BaseModel, Field

load_dotenv()
# ---------------------------------------------------------------------------
# Flow state
# ---------------------------------------------------------------------------

class GitHubAssistantState(BaseModel):
    """Shared state that travels through every stage of the flow."""

    # ── Inputs ──────────────────────────────────────────────────────────────
    query: str = Field(default="", description="Natural-language question about GitHub")
    github_repo: Optional[str] = Field(
        default=None,
        description="Optional 'owner/repo' to scope the search",
    )
    # GithubSearchTool requires gh_token to be passed explicitly.
    # We resolve it in initialize(): state.gh_token → GITHUB_TOKEN env-var.
    gh_token: str = Field(
        default="",
        description="GitHub PAT (falls back to GITHUB_TOKEN env-var if empty)",
    )

    # ── Intermediates / outputs ──────────────────────────────────────────────
    crew_result: str = Field(default="", description="Raw answer from the Crew")
    summary: str = Field(default="", description="Polished final answer")
    error: str = Field(default="", description="Error message if something went wrong")


class GroqSettings(BaseModel):
    api_key: str = Field(default="", description="Groq API Key")
    model: str = Field(default="llama-3.3-70b-versatile", description="The Groq model to use for processing.")
    temperature: float = Field(default=0.2, description="The temperature setting for the Groq model, controlling creativity.")
    max_tokens: int = Field(default=1000, description="The maximum number of tokens to generate in the response.")


class Settings(BaseSettings):
    groq: GroqSettings = Field(default_factory=GroqSettings)
    
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=[str(Path(__file__).resolve().parents[1] / ".env")],
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
        case_sensitive=False,
        frozen=True,
    )

settings = Settings()

def get_groq_client():
    return LLM(
        model=f"groq/{settings.groq.model}",  # LiteLLM requires the "groq/" prefix
        api_key=settings.groq.api_key,
        temperature=settings.groq.temperature,
        max_tokens=settings.groq.max_tokens,
    )


def normalize_github_repo(repo: str) -> str:
    """Normalize a GitHub repo reference to owner/repo format."""
    candidate = repo.strip()
    if not candidate:
        raise ValueError("GitHub repository must be a non-empty string.")

    url_patterns = [
        r"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$",
        r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
    ]
    for pattern in url_patterns:
        match = re.match(pattern, candidate, re.IGNORECASE)
        if match:
            owner = match.group("owner").strip()
            repo_name = match.group("repo").strip()
            return f"{owner}/{repo_name}"

    if "/" in candidate and candidate.count("/") == 1:
        owner, repo_name = candidate.split("/")
        if owner and repo_name:
            return candidate

    raise ValueError(
        "Invalid GitHub repository format. Use owner/repo or a GitHub repo URL "
        "such as https://github.com/owner/repo."
    )

# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------

class GitHubAssistantFlow(Flow[GitHubAssistantState]):
    """
    Three-stage CrewAI Flow wrapping a single ReAct Crew.

    Stage 1  →  @start        initialize()   – validate inputs & resolve token
    Stage 2  →  @listen(…)    search()       – run the ReAct crew
    Stage 3  →  @listen(…)    summarise()    – clean up & surface the answer
    """

    # -------------------------------------------------------------------------
    # Stage 1 – Initialise
    # -------------------------------------------------------------------------

    @start()
    def initialize(self) -> str:
        logger.info("=== GitHubAssistantFlow: initialize ===")
        logger.info(f"Query     : {self.state.query!r}")
        logger.info(f"Repo scope: {self.state.github_repo or 'none (global search)'}")

        if not self.state.query.strip():
            self.state.error = "No query provided – nothing to search for."
            logger.warning(self.state.error)
            return "error"

        # Resolve token: explicit state value wins, then env-var.
        token = self.state.gh_token.strip() or os.getenv("GITHUB_TOKEN", "").strip()
        if not token:
            self.state.error = (
                "A GitHub token is required. "
                "Set the GITHUB_TOKEN environment variable "
                "or pass gh_token=<your_token> to kickoff()."
            )
            logger.error(self.state.error)
            return "error"

        self.state.gh_token = token  # store resolved token for the next stage
        logger.info("GitHub token resolved ✓")
        return "initialized"

    # -------------------------------------------------------------------------
    # Stage 2 – Search (ReAct Crew)
    # -------------------------------------------------------------------------

    @listen(initialize)
    def search(self, event: str) -> str:
        if event == "error":
            logger.error("Skipping search – initialisation failed.")
            return "error"

        logger.info("=== GitHubAssistantFlow: search ===")

        # ── Build the tool ──────────────────────────────────────────────────
        # GithubSearchTool requires gh_token; pass it explicitly.
        tool_kwargs: dict = {"gh_token": self.state.gh_token}
        if self.state.github_repo:
            tool_kwargs["github_repo"] = self.state.github_repo

        github_tool = GithubSearchTool(**tool_kwargs)

        # ── ReAct Agent ─────────────────────────────────────────────────────
        react_agent = Agent(
            role="GitHub Research Specialist",
            goal=(
                "Answer the user's GitHub-related question as accurately and "
                "completely as possible by searching GitHub for relevant "
                "repositories, code, issues, and pull-requests."
            ),
            backstory=(
                "You are an expert software researcher with deep knowledge of "
                "the GitHub ecosystem. You excel at finding the right "
                "repositories, understanding open-source projects, and "
                "synthesising information from code, issues, and discussions."
            ),
            tools=[github_tool],
            verbose=True,
            # CrewAI agents use a ReAct loop by default:
            #   Thought → Action → Observation  (repeat until done)
            max_iter=10,            # cap iterations to avoid infinite loops
            max_rpm=20,             # cap LLM calls per minute
            allow_delegation=False,
        )

        # ── Task ────────────────────────────────────────────────────────────
        repo_scope_text = (
            f"Repository scope: {self.state.github_repo}\n\n"
            if self.state.github_repo
            else "Repository scope: none (global search)\n\n"
        )

        research_task = Task(
            description=(
                "Use the GithubSearchTool to answer the following question "
                "as thoroughly as possible.\n\n"
                f"{repo_scope_text}"
                f"Question: {self.state.query}\n\n"
                "Instructions:\n"
                "1. Search GitHub with relevant keywords.\n"
                "2. If a repository scope is provided, focus your search and analysis on that repo.\n"
                "3. Explore the most promising results (repos, issues, code).\n"
                "4. Gather code snippets, issue details, or repo stats as needed.\n"
                "5. Provide a clear, structured final answer with source links."
            ),
            expected_output=(
                "A detailed, well-structured answer containing:\n"
                "- Key findings\n"
                "- Relevant repository / issue / PR links\n"
                "- Code snippets where helpful\n"
                "- A concise summary paragraph"
            ),
            agent=react_agent,
        )

        # ── Crew (single-agent, sequential) ─────────────────────────────────
        crew = Crew(
            agents=[react_agent],
            tasks=[research_task],
            process=Process.sequential,
            verbose=True,
        )

        try:
            result = crew.kickoff()
            self.state.crew_result = str(result)
            logger.success("Crew finished successfully.")
            return "done"
        except Exception as exc:  # noqa: BLE001
            self.state.error = f"Crew execution failed: {exc}"
            logger.exception(self.state.error)
            return "error"

    # -------------------------------------------------------------------------
    # Stage 3 – Summarise
    # -------------------------------------------------------------------------

    @listen(search)
    def summarise(self, event: str) -> None:
        logger.info("=== GitHubAssistantFlow: summarise ===")

        if event == "error":
            self.state.summary = f"[ERROR] {self.state.error}"
            logger.error(self.state.summary)
            return

        raw = self.state.crew_result.strip()
        if not raw:
            self.state.summary = "The agent returned an empty result."
            logger.warning(self.state.summary)
            return

        max_chars = 8_000
        if len(raw) > max_chars:
            self.state.summary = raw[:max_chars] + "\n\n… [output truncated]"
        else:
            self.state.summary = raw

        logger.info("\n" + "─" * 60)
        logger.info("FINAL ANSWER:\n" + self.state.summary)
        logger.info("─" * 60)


# ---------------------------------------------------------------------------
# Public helpers (match pyproject.toml entry-points)
# ---------------------------------------------------------------------------

def kickoff(
    query: str,
    github_repo: Optional[str] = None,
    gh_token: Optional[str] = None,
) -> str:
    """
    Run the GitHubAssistantFlow and return the final answer.

    Parameters
    ----------
    query:
        Natural-language question, e.g.
        "What are the most starred Python async HTTP clients?"
    github_repo:
        Optional ``owner/repo`` or GitHub repo URL to narrow the search, e.g. ``"encode/httpx"`` or ``"https://github.com/encode/httpx"``.
    gh_token:
        GitHub personal-access token. Falls back to the ``GITHUB_TOKEN``
        environment variable when not supplied.

    Returns
    -------
    str
        The answer produced by the ReAct agent.

    Example
    -------
    >>> answer = kickoff("How does httpx handle retries?", github_repo="encode/httpx")
    >>> print(answer)
    """
    flow = GitHubAssistantFlow()
    flow.state.query = query
    if github_repo:
        flow.state.github_repo = normalize_github_repo(github_repo)
    if gh_token:
        flow.state.gh_token = gh_token

    flow.kickoff()
    return flow.state.summary


def plot() -> None:
    """Render a Mermaid diagram of the flow → github_assistant_flow.html."""
    flow = GitHubAssistantFlow()
    flow.plot("github_assistant_flow")
    logger.info("Flow diagram saved → github_assistant_flow.html")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="GitHub Assistant – CrewAI ReAct agent")
    parser.add_argument("query", help="Question to answer via GitHub search")
    parser.add_argument("--repo", default=None, metavar="OWNER/REPO|URL",
                        help="Narrow search to a specific repo using owner/repo or a GitHub URL (optional)")
    parser.add_argument("--token", default=None, metavar="GITHUB_PAT",
                        help="GitHub token (overrides GITHUB_TOKEN env-var)")
    parser.add_argument("--plot", action="store_true",
                        help="Render the flow diagram and exit")
    args = parser.parse_args()

    if args.plot:
        plot()
    else:
        print(args.query, args.repo, bool(args.token))
        answer = kickoff(query=args.query, github_repo=args.repo, gh_token=args.token)
        print("\n" + "═" * 60)
        print("ANSWER")
        print("═" * 60)
        print(answer)
