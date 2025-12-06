from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5432/orgos"
    openai_api_key: str = ""
    openai_model: str = "gpt-4"
    openai_max_retries: int = 3
    
    # Misalignment detection settings
    misalignment_threshold: float = 0.6  # Similarity below this is considered misalignment
    
    class Config:
        env_file = ".env"


settings = Settings()

