from __future__ import annotations

import pytest
from pydantic import ValidationError

from google_ads_agent.models import CampaignSelector, ExecutionControl, TextCondition
from google_ads_agent.utils import amount_to_micros, normalize_customer_id


def test_customer_id_normalization() -> None:
    assert normalize_customer_id("123-456-7890") == "1234567890"


def test_customer_id_rejects_invalid_value() -> None:
    with pytest.raises(Exception, match="10 digits"):
        normalize_customer_id("123")


def test_campaign_selector_requires_filter() -> None:
    with pytest.raises(ValidationError, match="at least one campaign filter"):
        CampaignSelector()


def test_execute_requires_explicit_approval() -> None:
    with pytest.raises(ValidationError, match="confirmation='APPROVE'"):
        ExecutionControl(mode="EXECUTE", plan_id="plan_123")


def test_regex_is_validated() -> None:
    with pytest.raises(ValidationError):
        TextCondition(operator="REGEX", value="[")


def test_amount_to_micros_is_exact() -> None:
    assert amount_to_micros("12.345678") == 12_345_678
    with pytest.raises(ValueError, match="six decimal"):
        amount_to_micros("1.0000001")
