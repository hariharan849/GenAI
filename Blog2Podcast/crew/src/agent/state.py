from crewai.flow.flow import FlowState

class BlogToPodcastState(FlowState):
    url: str = ""
    blog_content: str = ""
    podcast_script: str = ""
    audio_file: str = ""