import uuid
from loguru import logger
import opik
from src.observability.opik_utils import configure
from src.clients.firecrawl import get_firecrawl_client
from src.clients.grok import get_groq_client
from src.clients.elevenlabs import get_elevenlabs_client
from src.agent.prompt import get_summarization_prompt

configure()

log = logger.bind(tags=["blog2podcast-agent"])

@opik.track(name="scraping-url", capture_input=False, capture_output=False)
def scrape_blog_content_with_firecrawl(state):
    url = state.url if hasattr(state, "url") else state.get("url", "")
    client = get_firecrawl_client()
    response = client.scrape(url, formats=["markdown"], only_main_content=True)
    return {"blog_content": response.markdown}


@opik.track(name="summarizing-content", capture_input=False, capture_output=False)
def summarize_blog_content(state):
    blog_content = state.blog_content if hasattr(state, "blog_content") else state.get("blog_content", "")
    if not blog_content:
        return {}
    try:
        model = get_groq_client()
        prompt = get_summarization_prompt().prompt.format(blog_content=blog_content)
        response = model.invoke(prompt)
        return {"podcast_script": response.content.strip()}
    except Exception as e:
        log.error(f"Error during summarization: {e}")
        return {}


@opik.track(name="generating-audio", capture_input=False, capture_output=False)
def generate_audio(state):
    summary = state.podcast_script if hasattr(state, "podcast_script") else state.get("podcast_script", "")
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
    return {"audio_file": save_file_path}
