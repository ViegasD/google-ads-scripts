from __future__ import annotations

from pathlib import Path

import pytest

from google_ads_agent.config import AgentConfig
from google_ads_agent.plan_store import PlanStore
from google_ads_agent.service import GoogleAdsAgent
from tests.fakes import FakeAdsGateway, campaign, cta, geo


@pytest.fixture
def gateway() -> FakeAdsGateway:
    fake = FakeAdsGateway()
    fake.campaigns = [campaign()]
    fake.ctas = {"111": cta()}
    fake.geo_candidates = {("austin", "US"): [geo()]}
    return fake


@pytest.fixture
def agent(tmp_path: Path, gateway: FakeAdsGateway) -> GoogleAdsAgent:
    config = AgentConfig(plan_database_path=tmp_path / "plans.sqlite3")
    return GoogleAdsAgent(
        gateway,
        config=config,
        plan_store=PlanStore(config.plan_database_path),
    )
