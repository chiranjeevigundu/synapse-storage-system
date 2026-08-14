from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # No default, deliberately. This used to default to a literal key that was
    # committed to a public repository, which meant the ingest API accepted that
    # published key even with no .env present at all — a missing configuration
    # file silently produced a working, publicly-known credential. Required now,
    # so a missing value fails loudly at startup instead.
    API_KEY: str
    GEMINI_API_KEY: str = ""
    NAS_BASE_PATH: str = "/mnt/nas_data"
    KONG_GATEWAY_URL: str = "http://127.0.0.1:8000"
    LOG_LEVEL: str = "INFO"
    LEDGER_PATH: str = ""
    DRY_RUN: bool = True
    USE_LOCAL_LLM: bool = False
    OLLAMA_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "gemma4:e2b"

    @property
    def ledger_file_path(self) -> Path:
        if self.LEDGER_PATH:
            return Path(self.LEDGER_PATH)
        return Path(self.NAS_BASE_PATH) / "ledger.json"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
