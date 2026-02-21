from src.observability.prompt_versioning import Prompt

DEFAULT_PROMPT = """Summarize the following blog content and make it engaging and conversational:\n\n{blog_content}"""

def get_summarization_prompt():
    return Prompt(name="summarization_prompt", prompt=DEFAULT_PROMPT)