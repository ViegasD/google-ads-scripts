"""Application configuration without credential persistence."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class AgentConfig(BaseModel):
    """Runtime configuration for the Google Ads agent tools."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    api_version: str = "v25"
    plan_database_path: Path = Path(".google_ads_agent/plans.sqlite3")
    google_ads_yaml_path: Path | None = None
    default_plan_ttl_seconds: int = Field(default=900, ge=60, le=86_400)
    max_campaigns_hard_limit: int = Field(default=100, ge=1, le=1_000)
    max_operations_hard_limit: int = Field(default=1_000, ge=1, le=10_000)

    @classmethod
    def from_env(cls) -> AgentConfig:
        """Load non-secret settings.

        Google Ads credentials remain owned by the official client library and
        are loaded from its GOOGLE_ADS_* environment variables or YAML file.
        """

        yaml_value = os.getenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH")
        return cls(
            api_version=os.getenv("GOOGLE_ADS_API_VERSION", "v25"),
            plan_database_path=Path(
                os.getenv(
                    "GOOGLE_ADS_AGENT_PLAN_DB",
                    ".google_ads_agent/plans.sqlite3",
                )
            ),
            google_ads_yaml_path=Path(yaml_value) if yaml_value else None,
        )
