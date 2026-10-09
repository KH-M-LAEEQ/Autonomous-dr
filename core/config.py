"""Single source of truth for configuration. Read from .env, never from os.environ
scattered through the codebase.

Swapping an implementation of a frozen interface is a config change, not a code
change -- that is the whole point of Week 2. See `Settings.detector` etc.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "ci", "demo"] = "local"
    log_level: str = "INFO"

    # Persistence
    database_url: str = "postgresql+psycopg://adr:adr_dev_password@localhost:5432/adr"
    redis_url: str = "redis://localhost:6379/0"

    influx_url: str = "http://localhost:8086"
    influx_org: str = "autonomousdr"
    influx_bucket: str = "telemetry"

    influx_token: str = "dev-token-change-me"  # noqa: S105 -- local default, set in .env

    # API
    api_host: str = "0.0.0.0"  # noqa: S104 -- bound inside Docker only
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    # Pluggable implementations, selected at runtime
    providers: str = "simulated"
    detector: Literal["threshold", "iforest", "lstm", "ensemble", "gnn"] = "threshold"
    consensus: Literal["quorum", "pbft"] = "quorum"
    executor: Literal["simulated", "aws", "azure", "gcp", "terraform"] = "simulated"
    explainer: Literal["template", "llm"] = "template"

    # Monitor node identity (Week 17). Each node runs a DIFFERENT detector; they all
    # read the same telemetry, so independence is in the scoring method (ADR-0012).
    node_id: str = "node-a"
    node_detector: Literal["threshold", "iforest", "lstm", "gnn"] = "threshold"

    # Budget gate (Week 5)
    default_monthly_budget_usd: float = 25.0

    # Risk weight in the utility function (Week 22, ADR-0010). The score itself
    # updates autonomously; only the bound on its weight is a human-set policy.
    # Tenants may override at onboarding, same mechanism as the budget cap.
    w_risk_default: float = 0.10
    w_risk_min: float = 0.0
    w_risk_max: float = 0.30

    # Cloud credentials -- empty until Week 7
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_default_region: str = "us-east-1"
    groq_api_key: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def enabled_providers(self) -> list[str]:
        return [p.strip() for p in self.providers.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached so the .env file is parsed once per process."""
    return Settings()
