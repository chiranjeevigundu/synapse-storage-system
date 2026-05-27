from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    API_KEY: str = "super_secret_homelab_key"
    GEMINI_API_KEY: str = ""
    NAS_BASE_PATH: str = "/mnt/nas_data"
    KONG_GATEWAY_URL: str = "http://127.0.0.1:8000"
    LOG_LEVEL: str = "INFO"
    LEDGER_PATH: str = ""
    DRY_RUN: bool = True
    USE_LOCAL_LLM: bool = False
    OLLAMA_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "gemma2:2b"

    @property
    def ledger_file_path(self) -> Path:
        if self.LEDGER_PATH:
            return Path(self.LEDGER_PATH)
        return Path(self.NAS_BASE_PATH) / "ledger.json"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
