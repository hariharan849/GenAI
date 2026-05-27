from typing import Any, Dict, List
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

class CustomCostHandler(BaseCallbackHandler):
    def __init__(self, prompt_cost_per_token: float, completion_cost_per_token: float):
        self.prompt_cost = prompt_cost_per_token
        self.completion_cost = completion_cost_per_token
        self.total_cost = 0.0
        self.total_tokens = 0

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> Any:
        """Called when LLM finishes running."""
        token_usage = response.llm_output.get("token_usage", {})
        
        prompt_tokens = token_usage.get("prompt_tokens", 0)
        completion_tokens = token_usage.get("completion_tokens", 0)
        
        # Calculate cost
        cost = (prompt_tokens * self.prompt_cost) + (completion_tokens * self.completion_cost)
        self.total_cost += cost
        self.total_tokens += prompt_tokens + completion_tokens

        print(f"Tokens used - Prompt: {prompt_tokens}, Completion: {completion_tokens}")
        print(f"Cost of this call: ${cost:.5f}")
        print(f"Cumulative Total Cost: ${self.total_cost:.5f}")
