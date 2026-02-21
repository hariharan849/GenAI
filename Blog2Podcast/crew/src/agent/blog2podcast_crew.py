from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from src.clients.grok import get_groq_client

@CrewBase
class Blog2PodcastAssistantCrew:
    """Blog to Podcast Assistant Crew"""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"
    llm = get_groq_client()

    @agent
    def blog2podcast(self) -> Agent:
        return Agent(
            config=self.agents_config["blog2podcast"],
            llm=self.llm,
        )

    @task
    def analyze_blog(self) -> Task:
        return Task(
            config=self.tasks_config["analyze_blog"]
        )

    @crew
    def crew(self) -> Crew:
        """Creates the Blog to Podcast Crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
    
if __name__ == "__main__":
    output = (
        Blog2PodcastAssistantCrew()
        .crew()
        .kickoff(inputs={"blog_content": "hello"})
    )
    print(output)