from typing import ClassVar
from pathlib import Path
from pydantic import BaseModel, Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class GroqSettings(BaseModel):
    api_key: str = Field(default="", description="Groq API Key")
    model: str = Field(default="llama-3.3-70b-versatile", description="The Groq model to use for processing.")
    temperature: float = Field(default=0.2, description="The temperature setting for the Groq model, controlling creativity.")
    max_tokens: int = Field(default=1000, description="The maximum number of tokens to generate in the response.")


class LangfuseSettings(BaseModel):
    secret_key: str = Field(default="", description="Langfuse Secret Key")
    public_key: str = Field(default="", description="Langfuse Public Key")
    base_url: str = Field(default="https://cloud.langfuse.com", description="Langfuse base URL")
    project_name: str = Field(default="agentic-rag", description="Langfuse project name")

class Settings(BaseSettings):
    groq: GroqSettings = Field(default_factory=GroqSettings)
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=[str(Path(__file__).resolve().parents[1] / ".env")],
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
        case_sensitive=False,
        frozen=True,
    )

settings = Settings()
