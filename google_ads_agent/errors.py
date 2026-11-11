"""Stable, agent-readable errors."""

from __future__ import annotations

from typing import Any


class AgentToolError(Exception):
    """Base error with a stable machine-readable code."""

    code = "AGENT_TOOL_ERROR"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class InvalidCustomerIdError(AgentToolError):
    code = "INVALID_CUSTOMER_ID"


class AmbiguousSelectorError(AgentToolError):
    code = "AMBIGUOUS_SELECTOR"


class UnsupportedSelectorError(AgentToolError):
    code = "UNSUPPORTED_SELECTOR"


class SafetyLimitError(AgentToolError):
    code = "SAFETY_LIMIT_EXCEEDED"


class GeoResolutionError(AgentToolError):
    code = "GEO_RESOLUTION_ERROR"


class TargetingConflictError(AgentToolError):
    code = "TARGETING_CONFLICT"


class PlanNotFoundError(AgentToolError):
    code = "PLAN_NOT_FOUND"


class PlanExpiredError(AgentToolError):
    code = "PLAN_EXPIRED"


class PlanStateError(AgentToolError):
    code = "INVALID_PLAN_STATE"


class PlanInputMismatchError(AgentToolError):
    code = "PLAN_INPUT_MISMATCH"


class StalePlanError(AgentToolError):
    code = "STALE_PLAN"


class IdempotencyConflictError(AgentToolError):
    code = "IDEMPOTENCY_CONFLICT"


class GoogleAdsDependencyError(AgentToolError):
    code = "GOOGLE_ADS_DEPENDENCY_ERROR"


class GoogleAdsRequestError(AgentToolError):
    code = "GOOGLE_ADS_REQUEST_FAILED"
