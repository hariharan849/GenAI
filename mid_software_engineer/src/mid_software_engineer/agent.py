"""DeepAgents factory for a mid-level software engineer workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

from .tracing import (
    DEFAULT_TRACE_DB,
    AgentTraceStore,
    configure_langsmith,
    create_trace_middleware,
)


DEFAULT_GSTACK_SKILLS: tuple[str, ...] = (
    "C:/Users/HARI/.agents/skills/office-hours/",
    "C:/Users/HARI/.agents/skills/autoplan/",
    "C:/Users/HARI/.agents/skills/ship/",
)


MID_SOFTWARE_ENGINEER_SYSTEM_PROMPT = """\
You are a pragmatic mid-level software engineer agent.

Operating model:
1. Product-owner intake: restate the requirement, identify the user, success criteria,
   constraints, and open questions. Ask only for missing information that blocks a safe
   implementation.
2. Discovery: inspect the repository before proposing code. Prefer existing patterns,
   tests, and tooling over new abstractions.
3. Design flow: write a concise design proposal before implementation. Include the
   requirement, proposed flow, touched modules, test strategy, demo path, risks, and
   explicit architect-approval criteria.
4. Architect approval gate: do not start implementation until the design is approved
   by the user or the task explicitly says approval can be assumed.
5. Implementation: make small, coherent edits. Keep behavior scoped to the approved
   requirement.
6. Unit tests: add or update focused tests for the changed behavior. Run the relevant
   tests and fix failures before claiming completion.
7. Demo: provide a concrete command, script, API call, or walkthrough that demonstrates
   the requirement working.
8. Ship readiness: summarize verification evidence, changed files, unresolved risks,
   and the next shipping action.

Skill usage:
- Use the office-hours skill when the requirement needs product shaping, demand
  validation, or tradeoff exploration.
- Use the autoplan skill after the design proposal exists and before implementation
  when a plan review or architect-style approval is needed.
- Use the ship skill only after implementation and tests pass, when the user asks to
  ship, package, push, deploy, or create a PR.

Engineering standards:
- Be direct and concrete.
- Prefer boring, maintainable code.
- Preserve unrelated user changes.
- Never claim tests passed unless you ran them in the current state.
- If a global gstack skill contains host-specific instructions that cannot run in this
  environment, adapt its intent to the DeepAgents tool surface and explain the gap.
"""


def create_mid_software_engineer_agent(
    *,
    model: str = "openai:gpt-5.4",
    backend_root: str | Path = ".",
    skills: Sequence[str] | None = None,
    tools: Sequence[Any] | None = None,
    checkpointer: Any | None = None,
    interrupt_on: dict[str, Any] | None = None,
    middleware: Sequence[Any] | None = None,
    debug: bool = False,
) -> Any:
    """Create the LangChain DeepAgent configured for this workflow.

    Imports DeepAgents lazily so tests can validate configuration without requiring
    provider credentials or importing the package at module import time.
    """

    from deepagents import create_deep_agent
    from deepagents.backends.filesystem import FilesystemBackend

    skill_paths = list(skills or DEFAULT_GSTACK_SKILLS)
    validate_skill_paths(skill_paths)

    backend = FilesystemBackend(
        root_dir=str(Path(backend_root).resolve()),
        virtual_mode=False,
    )

    return create_deep_agent(
        model=model,
        tools=list(tools or ()),
        system_prompt=MID_SOFTWARE_ENGINEER_SYSTEM_PROMPT,
        backend=backend,
        skills=skill_paths,
        checkpointer=checkpointer,
        interrupt_on=interrupt_on,
        middleware=list(middleware or ()),
        debug=debug,
        name="mid-software-engineer",
    )


def create_local_development_agent(
    *,
    model: str = "openai:gpt-5.4",
    backend_root: str | Path = ".",
    skills: Sequence[str] | None = None,
    tools: Sequence[Any] | None = None,
    trace_store: AgentTraceStore | None = None,
    trace_db_path: str | Path | None = None,
    debug: bool = False,
) -> Any:
    """Create the agent with coding middleware and human-in-loop safeguards."""

    from langchain_quickjs import CodeInterpreterMiddleware
    from langgraph.checkpoint.memory import MemorySaver

    configure_langsmith()
    store = trace_store or AgentTraceStore(trace_db_path or DEFAULT_TRACE_DB)

    return create_mid_software_engineer_agent(
        model=model,
        backend_root=backend_root,
        skills=skills,
        tools=tools,
        checkpointer=MemorySaver(),
        interrupt_on=default_interrupt_on(),
        middleware=[CodeInterpreterMiddleware(), create_trace_middleware(store)],
        debug=debug,
    )


def default_interrupt_on() -> dict[str, Any]:
    """Default human-in-loop policy for local development.

    The DeepAgents runtime adds HumanInTheLoopMiddleware when this mapping is
    provided. File reads stay automatic; writes and edits pause for approval.
    """

    return {
        "write_file": {"allowed_decisions": ["approve", "edit", "reject"]},
        "edit_file": {"allowed_decisions": ["approve", "edit", "reject"]},
    }


def validate_skill_paths(skill_paths: Iterable[str]) -> None:
    """Fail early when a configured global gstack skill is missing."""

    missing = [
        path
        for path in skill_paths
        if not (Path(path) / "SKILL.md").exists()
    ]
    if missing:
        formatted = ", ".join(missing)
        raise FileNotFoundError(f"Missing SKILL.md for configured skill path(s): {formatted}")
