from typing import TypedDict

class BlogToPodcastState(TypedDict):
    url: str
    blog_content: str
    podcast_script: str
    audio_file: str