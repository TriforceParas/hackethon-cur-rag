from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Multi Mode AI Agent"
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_api_key: str = ""
    ollama_think: str = "low"
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    vector_db: str = "faiss"
    sqlite_db_path: Path = Field(default=Path("./data/app.db"))
    upload_dir: Path = Field(default=Path("./data/uploads"))
    vectorstore_dir: Path = Field(default=Path("./data/vectorstore"))
    top_k: int = 5
    rag_min_score: float = 0.35
    web_search_provider: str = "ollama"
    debug_errors: bool = False

    @property
    def normalized_provider(self) -> str:
        return self.llm_provider.strip().lower()


@lru_cache
def get_settings() -> Settings:
    return Settings()
