"""CLI demo for the mid software engineer DeepAgent."""

from __future__ import annotations

import argparse
from dotenv import load_dotenv
from pprint import pprint
load_dotenv()

from .agent import DEFAULT_GSTACK_SKILLS, create_mid_software_engineer_agent


SAMPLE_REQUIREMENT = (
    "Product owner request: create a small CLI that accepts a requirement, proposes "
    "a design for architect approval, implements after approval, writes unit tests, "
    "and prints a demo command."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create and optionally invoke the DeepAgent demo.")
    parser.add_argument("--model", default="openai:gpt-5.4", help="DeepAgents model string.")
    parser.add_argument("--thread-id", default="demo", help="LangGraph thread id for invocation.")
    parser.add_argument("--construct", action="store_true", help="Construct the real DeepAgent object.")
    parser.add_argument("--invoke", action="store_true", help="Invoke the agent with a sample request.")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    print("Mid software engineer DeepAgent configuration")
    print(f"Model: {args.model}")
    print("Skills:")
    for skill in DEFAULT_GSTACK_SKILLS:
        print(f"- {skill}")
    print("Workflow gates:")
    for gate in ("Product-owner intake", "Design flow", "Architect approval gate", "Unit tests", "Demo"):
        print(f"- {gate}")

    if not (args.construct or args.invoke):
        print("Use --construct to build the real agent, or --invoke to run the sample requirement.")
        return

    agent = create_mid_software_engineer_agent(model=args.model)
    print("Constructed DeepAgent.")
    if not args.invoke:
        return

    result = agent.invoke(
        {"messages": [{"role": "user", "content": SAMPLE_REQUIREMENT}]},
        config={"configurable": {"thread_id": args.thread_id}},
    )
    pprint(result)


if __name__ == "__main__":
    main()
