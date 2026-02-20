from typing import ClassVar
from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GroqSettings(BaseModel):
    api_key: str = Field(default="", description="Groq API Key")
    model: str = Field(default="llama-3.3-70b-versatile", description="The Groq model to use for processing.")
    temperature: float = Field(default=0.2, description="The temperature setting for the Groq model, controlling creativity.")
    max_tokens: int = Field(default=1000, description="The maximum number of tokens to generate in the response.")

class ElevenLabsSettings(BaseModel):
    api_key: str = Field(default="", description="ElevenLabs API Key")
    voice_id: str = Field(default="pNInz6obpgDQGcFmaJgB", description="The ID of the voice to use for text-to-speech conversion.")
    optimize_streaming_latency: str = Field(default="0", description="The streaming latency optimization setting for ElevenLabs.")
    output_format: str = Field(default="mp3_22050_32", description="The output format for the audio file.")
    model_id: str = Field(default="eleven_multilingual_v2", description="The ElevenLabs model ID to use for text-to-speech conversion.")

class FirecrawlSettings(BaseModel):
    api_key: str = Field(default="", description="Firecrawl API Key")

class OpikSettings(BaseModel):
    api_key: str = Field(default="", description="Opik API Key")
    project_name: str = Field(default="", description="Opik Project Name")

class Settings(BaseSettings):
    groq: GroqSettings = Field(default_factory=GroqSettings)
    eleven_labs: ElevenLabsSettings = Field(default_factory=ElevenLabsSettings)
    firecrawl: FirecrawlSettings = Field(default_factory=FirecrawlSettings)
    opik: OpikSettings = Field(default_factory=OpikSettings)
    
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=[str(Path(__file__).resolve().parents[1] / ".env")],
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
        case_sensitive=False,
        frozen=True,
    )

settings = Settings()
