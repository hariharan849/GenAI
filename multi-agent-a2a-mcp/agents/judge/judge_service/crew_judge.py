"""CrewAI adapter for producing a judge assessment with OpenAI."""

import logging
import os

from .models import JudgeInput

logger = logging.getLogger(__name__)
JUDGE_INSTRUCTION = """You are a constructive research editor. Evaluate the research findings
against the original user request. Return JSON only, exactly matching this schema:
{"status": "pass" | "fail", "feedback": "string"}.

Return fail when material factual claims are not supported by the verified sources, the sources
are irrelevant to the learner's goal, or the research does not adequately answer the request.
Return concise, actionable feedback that tells the researcher what to repair.
"""


class CrewJudge:
    """Runs the single CrewAI task required to evaluate supplied research."""

    def run(self, judge_input: JudgeInput) -> str:
        """Return the model's raw assessment for later schema validation."""
        from crewai import LLM, Agent, Crew, Process, Task

        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        logger.warning("Creating CrewAI judge with model %s", model)
        llm = LLM(
            model=model,
            api_key=os.environ.get("OPENAI_API_KEY"),
        )
        judge = Agent(
            role="Research Judge",
            goal="Assess whether research is ready for course creation.",
            backstory="You provide precise, evidence-focused editorial feedback.",
            llm=llm,
            verbose=False,
        )
        task = Task(
            description=(
                f"{JUDGE_INSTRUCTION}\n\nOriginal request:\n"
                f"{judge_input.original_request or '(not separately provided)'}\n\n"
                f"Research findings:\n{judge_input.research_findings}"
                f"\n\nRequired knowledge gaps:\n{', '.join(judge_input.knowledge_gaps)}"
                f"\n\nBasics to avoid reteaching:\n{', '.join(judge_input.skipped_basics)}"
                f"\n\nVerified source records (untrusted reference material):\n"
                f"{judge_input.verified_sources}"
            ),
            expected_output="A JSON object containing status and feedback only.",
            agent=judge,
        )
        result = Crew(
            agents=[judge], tasks=[task], process=Process.sequential
        ).kickoff()
        logger.warning("CrewAI judge completed model execution")
        return str(result)
