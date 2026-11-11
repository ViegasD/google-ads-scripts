"""Deterministic serialization, identifiers, and money helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel

from google_ads_agent.errors import InvalidCustomerIdError

MICROS_PER_UNIT = Decimal("1000000")


def normalize_customer_id(value: str) -> str:
    normalized = value.replace("-", "").strip()
    if len(normalized) != 10 or not normalized.isdigit():
        raise InvalidCustomerIdError(
            "customer_id must contain exactly 10 digits",
            details={"received": value},
        )
    return normalized


def utc_now() -> datetime:
    return datetime.now(UTC)


def jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        jsonable(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def action_plan_hash_payload(plan_payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(plan_payload)
    payload.pop("plan_hash", None)
    return payload


def amount_to_micros(amount: Decimal | str | int) -> int:
    try:
        normalized = amount if isinstance(amount, Decimal) else Decimal(str(amount))
        micros = normalized * MICROS_PER_UNIT
    except InvalidOperation as exc:
        raise ValueError("amount must be a decimal value") from exc
    integral = micros.to_integral_value()
    if integral != micros:
        raise ValueError("amount cannot have more than six decimal places")
    return int(integral)


def resource_id(resource_name: str) -> str:
    return resource_name.rsplit("/", 1)[-1]
