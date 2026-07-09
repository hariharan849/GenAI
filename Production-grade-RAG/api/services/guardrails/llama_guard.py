import httpx

from api.services.ollama.client import OllamaClient

from .models import LlamaGuardResult


INPUT_PROMPT_TEMPLATE = """Task: Check if the user message is safe.

User message:
{prompt}

Respond with exactly one of:
safe
unsafe
If unsafe, include categories on following lines."""


OUTPUT_PROMPT_TEMPLATE = """Task: Check if the assistant response is safe for the user request.

User message:
{prompt}

Assistant response:
{response}

Respond with exactly one of:
safe
unsafe
If unsafe, include categories on following lines."""


class LlamaGuardClassifier:
    """Llama Guard classifier backed by the local Ollama API."""

    def __init__(self, ollama_client: OllamaClient, model: str, timeout_seconds: float):
        self.ollama_client = ollama_client
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def ensure_model_available(self) -> bool:
        models = await self.ollama_client.list_models()
        names = {
            model.get("name") or model.get("model")
            for model in models
            if isinstance(model, dict)
        }
        return self.model in names

    async def classify_input(self, prompt: str) -> LlamaGuardResult:
        return self.parse_response(
            await self._generate(INPUT_PROMPT_TEMPLATE.format(prompt=prompt))
        )

    async def classify_output(self, prompt: str, response: str) -> LlamaGuardResult:
        return self.parse_response(
            await self._generate(OUTPUT_PROMPT_TEMPLATE.format(prompt=prompt, response=response))
        )

    async def _generate(self, prompt: str) -> str:
        timeout = httpx.Timeout(float(self.timeout_seconds))
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self.ollama_client.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False, "temperature": 0.0},
            )
            response.raise_for_status()
            payload = response.json()
            return str(payload.get("response", ""))

    @staticmethod
    def parse_response(raw_response: str) -> LlamaGuardResult:
        lines = [line.strip() for line in raw_response.strip().splitlines() if line.strip()]
        if not lines:
            raise ValueError("empty Llama Guard response")

        verdict = lines[0].lower()
        categories: list[str] = []
        for line in lines[1:]:
            categories.extend(part.strip() for part in line.replace(",", " ").split() if part.strip())

        if verdict.startswith("safe"):
            return LlamaGuardResult(safe=True, raw_response=raw_response, reason="Llama Guard classified content as safe")
        if verdict.startswith("unsafe"):
            return LlamaGuardResult(
                safe=False,
                categories=categories,
                raw_response=raw_response,
                reason="Llama Guard classified content as unsafe",
            )

        raise ValueError(f"unrecognized Llama Guard response: {raw_response!r}")
