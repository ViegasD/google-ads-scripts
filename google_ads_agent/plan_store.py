"""SQLite-backed immutable plans and audit records."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from google_ads_agent.errors import (
    IdempotencyConflictError,
    PlanExpiredError,
    PlanNotFoundError,
    PlanStateError,
)
from google_ads_agent.models import ActionPlan, ActionResult, StoredPlanStatus
from google_ads_agent.utils import (
    action_plan_hash_payload,
    canonical_json,
    stable_hash,
    utc_now,
)


class PlanStore:
    """Persist plans, enforce single-use execution, and journal outcomes."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS plans (
                    plan_id TEXT PRIMARY KEY,
                    tool_name TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL,
                    plan_hash TEXT NOT NULL,
                    idempotency_key TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    result_json TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS plans_idempotency
                ON plans(tool_name, customer_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL;

                CREATE TABLE IF NOT EXISTS audit_journal (
                    journal_id TEXT PRIMARY KEY,
                    plan_id TEXT,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    FOREIGN KEY(plan_id) REFERENCES plans(plan_id)
                );
                """
            )

    @staticmethod
    def _verify_hash(plan: ActionPlan) -> None:
        payload = plan.model_dump(mode="json")
        calculated = stable_hash(action_plan_hash_payload(payload))
        if calculated != plan.plan_hash:
            raise PlanStateError(
                "stored plan failed its integrity check",
                details={"plan_id": plan.plan_id},
            )

    def save_plan(
        self,
        plan: ActionPlan,
        *,
        idempotency_key: str | None,
    ) -> ActionPlan:
        self._verify_hash(plan)
        now = utc_now().isoformat()
        plan_json = canonical_json(plan)
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO plans (
                        plan_id, tool_name, customer_id, status,
                        request_fingerprint, plan_hash, idempotency_key,
                        created_at, expires_at, plan_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        plan.plan_id,
                        plan.tool_name,
                        plan.customer_id,
                        StoredPlanStatus.VALIDATED.value,
                        plan.request_fingerprint,
                        plan.plan_hash,
                        idempotency_key,
                        plan.created_at.isoformat(),
                        plan.expires_at.isoformat(),
                        plan_json,
                        now,
                    ),
                )
        except sqlite3.IntegrityError:
            if idempotency_key is None:
                raise
            existing = self.find_by_idempotency_key(
                plan.tool_name,
                plan.customer_id,
                idempotency_key,
            )
            if existing.request_fingerprint != plan.request_fingerprint:
                raise IdempotencyConflictError(
                    "idempotency key was already used for different inputs",
                    details={"idempotency_key": idempotency_key},
                ) from None
            return existing
        self.add_audit_event(plan.plan_id, "PLAN_VALIDATED", {"plan_hash": plan.plan_hash})
        return plan

    def get_plan(self, plan_id: str) -> ActionPlan:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT plan_json FROM plans WHERE plan_id = ?",
                (plan_id,),
            ).fetchone()
        if row is None:
            raise PlanNotFoundError("plan was not found", details={"plan_id": plan_id})
        plan = ActionPlan.model_validate_json(row["plan_json"])
        self._verify_hash(plan)
        return plan

    def find_by_idempotency_key(
        self,
        tool_name: str,
        customer_id: str,
        idempotency_key: str,
    ) -> ActionPlan:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT plan_json FROM plans
                WHERE tool_name = ? AND customer_id = ? AND idempotency_key = ?
                """,
                (tool_name, customer_id, idempotency_key),
            ).fetchone()
        if row is None:
            raise PlanNotFoundError("idempotent plan was not found")
        plan = ActionPlan.model_validate_json(row["plan_json"])
        self._verify_hash(plan)
        return plan

    def claim_execution(self, plan_id: str) -> tuple[ActionPlan, ActionResult | None]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM plans WHERE plan_id = ?",
                (plan_id,),
            ).fetchone()
            if row is None:
                raise PlanNotFoundError("plan was not found", details={"plan_id": plan_id})

            status = StoredPlanStatus(row["status"])
            if status in {StoredPlanStatus.EXECUTED, StoredPlanStatus.PARTIAL}:
                result = ActionResult.model_validate_json(row["result_json"])
                return ActionPlan.model_validate_json(row["plan_json"]), result
            if status != StoredPlanStatus.VALIDATED:
                raise PlanStateError(
                    f"plan cannot execute from state {status.value}",
                    details={"plan_id": plan_id, "status": status.value},
                )

            expires_at = datetime.fromisoformat(row["expires_at"])
            if expires_at <= utc_now():
                raise PlanExpiredError(
                    "plan approval window has expired",
                    details={"plan_id": plan_id, "expires_at": row["expires_at"]},
                )

            connection.execute(
                "UPDATE plans SET status = ?, updated_at = ? WHERE plan_id = ?",
                (StoredPlanStatus.EXECUTING.value, utc_now().isoformat(), plan_id),
            )

        plan = ActionPlan.model_validate_json(row["plan_json"])
        self._verify_hash(plan)
        self.add_audit_event(plan_id, "EXECUTION_CLAIMED", {})
        return plan, None

    def finish_execution(
        self,
        plan_id: str,
        result: ActionResult,
        *,
        status: StoredPlanStatus,
    ) -> None:
        if status not in {
            StoredPlanStatus.EXECUTED,
            StoredPlanStatus.PARTIAL,
            StoredPlanStatus.STALE,
            StoredPlanStatus.FAILED,
        }:
            raise ValueError(f"unsupported terminal plan status: {status}")
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE plans
                SET status = ?, result_json = ?, updated_at = ?
                WHERE plan_id = ? AND status = ?
                """,
                (
                    status.value,
                    canonical_json(result),
                    utc_now().isoformat(),
                    plan_id,
                    StoredPlanStatus.EXECUTING.value,
                ),
            )
            if cursor.rowcount != 1:
                raise PlanStateError(
                    "plan execution state changed unexpectedly",
                    details={"plan_id": plan_id},
                )
        self.add_audit_event(
            plan_id,
            f"EXECUTION_{status.value}",
            result.model_dump(mode="json"),
        )

    def add_audit_event(
        self,
        plan_id: str | None,
        event_type: str,
        details: dict[str, Any],
    ) -> str:
        journal_id = f"journal_{uuid.uuid4().hex}"
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO audit_journal (
                    journal_id, plan_id, event_type, occurred_at, details_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    journal_id,
                    plan_id,
                    event_type,
                    utc_now().isoformat(),
                    canonical_json(details),
                ),
            )
        return journal_id

    def get_status(self, plan_id: str) -> StoredPlanStatus:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT status FROM plans WHERE plan_id = ?",
                (plan_id,),
            ).fetchone()
        if row is None:
            raise PlanNotFoundError("plan was not found", details={"plan_id": plan_id})
        return StoredPlanStatus(row["status"])
