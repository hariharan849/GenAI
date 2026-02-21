from elevenlabs.client import ElevenLabs
from src.config import settings

def get_elevenlabs_client():
    return ElevenLabs(api_key=settings.eleven_labs.api_key)