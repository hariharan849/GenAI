from crewai import LLM
from src.config import settings

def get_groq_client():
    return LLM(
        model=f"groq/{settings.groq.model}",  # LiteLLM requires the "groq/" prefix
        api_key=settings.groq.api_key,
        temperature=settings.groq.temperature,
        max_tokens=settings.groq.max_tokens,
    )

if __name__ == "__main__":
    client = get_groq_client()
    response = client.chat("What is the capital of France?")
    print(response)