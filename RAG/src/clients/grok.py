
import sys
sys.path.append(r"E:\GitHub\GenerativeAI\RAG")
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
    from src.callbacks.cost_handler import CustomCostHandler
    from src.callbacks.langfuse_handler import langfuse_handler
    messages = [
        (
            "system",
            "You are a helpful assistant that translates English to French. Translate the user sentence.",
        ),
        ("human", "I love programming."),
    ]
    callbacks = [
        CustomCostHandler(prompt_cost_per_token=0.0001, completion_cost_per_token=0.0002),
    ]
    callbacks.append(langfuse_handler)

    ai_msg = client.invoke(
        messages,
        config={
            "callbacks": callbacks
        }
    )
    print(ai_msg)