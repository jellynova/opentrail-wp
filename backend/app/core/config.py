from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg2://opentrail:opentrail@db:5432/opentrail"
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    FERNET_KEY: str = "change-me-generate-with-Fernet.generate_key()"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    ALLOWED_ORIGINS: List[str] = ["http://localhost", "http://localhost:3000", "http://localhost:5173"]
    DOCUMENTS_PATH: str = "/app/documents"
    DEBUG: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
