import uuid
from loguru import logger
import opik
from crewai.flow.flow import Flow, listen, start

from src.agent.state import BlogToPodcastState
from src.observability.opik_utils import configure
from src.clients.firecrawl import get_firecrawl_client
from src.clients.elevenlabs import get_elevenlabs_client
from src.agent.blog2podcast_crew import Blog2PodcastAssistantCrew

configure()

log = logger.bind(tags=["blog2podcast-agent"])


class Blog2PodcastFlow(Flow[BlogToPodcastState]):

    @start()
    @opik.track(name="scraping-url", capture_input=False, capture_output=False)
    def scrape_blog_content_with_firecrawl(self):
        url = self.state.url
        log.info(f"Scraping content from URL: {url}")
        client = get_firecrawl_client()
        response = client.scrape(url, formats=["markdown"], only_main_content=True)
        self.state.blog_content = response.markdown

    @listen(scrape_blog_content_with_firecrawl)
    @opik.track(name="summarizing-content", capture_input=False, capture_output=False)
    def summarize_blog_content(self):
        blog_content = self.state.blog_content
        log.info(f"Summarizing blog content of length {len(blog_content)} characters")
        if not blog_content:
            return {}
        try:
            output = (
                Blog2PodcastAssistantCrew()
                .crew()
                .kickoff(inputs={"blog_content": blog_content})
            )
            self.state.podcast_script = output.raw
        except Exception as e:
            log.error(f"Error during summarization: {e}")
            return {}

    @listen(summarize_blog_content)
    @opik.track(name="generating-audio", capture_input=False, capture_output=False)
    def generate_audio(self):
        summary = self.state.podcast_script
        log.info(f"Generating audio from podcast script of length {len(summary)} characters")
        if not summary:
            return {}
        client = get_elevenlabs_client()
        audio = client.text_to_speech.convert(
            voice_id="pNInz6obpgDQGcFmaJgB",  # Adam pre-made voice
            optimize_streaming_latency="0",
            output_format="mp3_22050_32",
            text=summary,
            model_id="eleven_multilingual_v2",
        )
        # Generating a unique file name for the output MP3 file
        save_file_path = f"{uuid.uuid4()}.mp3"
        # Writing the audio stream to the file

        with open(save_file_path, "wb") as f:
            for chunk in audio:
                if chunk:
                    f.write(chunk)
        self.state.audio_file = save_file_path

def kickoff(url: str) -> dict:
    """
    Run the flow.
    """
    blog2podcast_flow = Blog2PodcastFlow()
    blog2podcast_flow.state.url = url
    blog2podcast_flow.kickoff()
    return blog2podcast_flow.state.dict()

def plot():
    """
    Plot the flow.
    """
    blog2podcast_flow = Blog2PodcastFlow()
    blog2podcast_flow.plot()


if __name__ == "__main__":
    print(kickoff("https://machinelearningmastery.com/contact/"))
    # plot()