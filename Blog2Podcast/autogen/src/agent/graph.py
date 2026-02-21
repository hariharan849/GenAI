from opik.integrations.langchain import OpikTracer
from opik import opik_context
import opik
from loguru import logger

from src.agent.state import BlogToPodcastState
from src.agent.nodes import scrape_blog_content_with_firecrawl, summarize_blog_content, generate_audio
from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

def construct_blog_to_podcast_graph():
     graph = StateGraph(BlogToPodcastState)
     graph.add_node("scrape", scrape_blog_content_with_firecrawl)
     graph.add_node("summarize", summarize_blog_content)
     graph.add_node("generate", generate_audio)
     graph.add_edge("scrape", "summarize")
     graph.add_edge("summarize", "generate")
     graph.add_edge("generate", END)
     graph.set_entry_point("scrape")

     memory = MemorySaver()
     return graph.compile(checkpointer=memory)


class BlogToPodcastGraph:
    def __init__(self, url, thread_id: str = "default"):
        self.thread_id = thread_id
        self._opik_tracer = OpikTracer(
            tags=["blog2podcast-agent"],
            thread_id=thread_id,
        )
        self.graph = construct_blog_to_podcast_graph()
        self.state = BlogToPodcastState(url=url)
     
    def invoke(self):
        state = self.graph.invoke(self.state, {
                "configurable": {"thread_id": self.thread_id},
                "callbacks": [self._opik_tracer]
            })
        return state
    

if __name__ == "__main__":
     graph = BlogToPodcastGraph(url="https://www.bbc.com/news/world-europe-60506682")
     output = graph.invoke()
     logger.info(f"Final output: {output}")