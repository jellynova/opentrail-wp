from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg2://opentrail:opentrail@db:5432/opentrail"
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    FERNET_KEY: str = "change-me-generate-with-Fernet.generate_key()"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    # Comma-separated in the environment (pydantic-settings cannot JSON-decode a bare
    # string into List[str], which used to make the app fail to start on the documented
    # .env). Read it through `allowed_origins`.
    ALLOWED_ORIGINS: str = "http://localhost,http://localhost:3000,http://localhost:5173"
    DOCUMENTS_PATH: str = "/app/documents"
    DEBUG: bool = False
    ORGANIZATION_NAME: str = "Municipality"  # shown on financial statement headings
    # Journal entry balance enforcement on posting: "block" rejects unbalanced entries,
    # "warn" allows them (the response's is_balanced flag reports the imbalance).
    JE_BALANCE_ENFORCEMENT: str = "block"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def allowed_origins(self) -> List[str]:
        """CORS origins, split from the comma-separated ALLOWED_ORIGINS setting."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


settings = Settings()
