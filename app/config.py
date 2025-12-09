from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/orgos",
        validation_alias="DATABASE_URL"  # Explicitly read DATABASE_URL from env
    )
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_model: str = "gpt-5-mini"  # Latest 2025 model with 400K context window!
    openai_max_retries: int = 3
    
    # Misalignment detection settings
    misalignment_threshold: float = 0.6  # Similarity below this is considered misalignment
    
    class Config:
        env_file = ".env"
        case_sensitive = False  # Allow case-insensitive env var names


settings = Settings()

