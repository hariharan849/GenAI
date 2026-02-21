
from langchain_groq import ChatGroq
from src.config import settings

def get_groq_client():
    return ChatGroq(
            model=settings.groq.model,
            api_key=settings.groq.api_key,
            temperature=settings.groq.temperature,
            max_tokens=settings.groq.max_tokens,
        )

if __name__ == "__main__":
    client = get_groq_client()
    response = client.chat("What is the capital of France?")
    print(response)