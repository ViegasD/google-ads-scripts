from __future__ import annotations

from pathlib import Path

from google_ads_agent.models import StoredPlanStatus
from google_ads_agent.plan_store import PlanStore


def test_store_initializes_sqlite_schema(tmp_path: Path) -> None:
    store = PlanStore(tmp_path / "plans.sqlite3")

    assert (tmp_path / "plans.sqlite3").exists()
    journal_id = store.add_audit_event(None, "TEST", {"ok": True})
    assert journal_id.startswith("journal_")


def test_stored_status_enum_values_are_stable() -> None:
    assert StoredPlanStatus.VALIDATED.value == "VALIDATED"
