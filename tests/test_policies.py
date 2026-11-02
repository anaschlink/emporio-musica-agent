from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from emporio.policies import (
    POLICY_FILES,
    all_policies_text,
    get_policy,
    load_policies,
)

TZ = ZoneInfo("America/Campo_Grande")


@pytest.fixture
def policies():
    return {
        topic: f"Policy content for {topic}"
        for topic in POLICY_FILES
    }


def test_load_policies(tmp_path):
    for filename in POLICY_FILES.values():
        (tmp_path / filename).write_text("Policy content", encoding="utf-8")

    result = load_policies(tmp_path)

    assert len(result) == len(POLICY_FILES)
    assert result["payment"] == "Policy content"


def test_load_policies_rejects_empty_file(tmp_path):
    for filename in POLICY_FILES.values():
        (tmp_path / filename).write_text("Policy content", encoding="utf-8")

    (tmp_path / "payment.md").write_text("", encoding="utf-8")

    with pytest.raises(ValueError):
        load_policies(tmp_path)


def test_unknown_topic(policies):
    result = get_policy("unknown", policies)

    assert result["success"] is False
    assert result["error"] == "unknown_topic"


def test_get_policy(policies):
    result = get_policy("payment", policies)

    assert result["success"] is True
    assert result["content"] == "Policy content for payment"


@pytest.mark.parametrize(
    "date,expected",
    [
        (datetime(2026, 11, 2, 10, 0, tzinfo=TZ), True),   # Monday
        (datetime(2026, 11, 2, 18, 0, tzinfo=TZ), False),  # Closing time
        (datetime(2026, 11, 7, 12, 0, tzinfo=TZ), True),   # Saturday
        (datetime(2026, 11, 7, 13, 0, tzinfo=TZ), False),  # Saturday closing
        (datetime(2026, 11, 8, 10, 0, tzinfo=TZ), False),  # Sunday
    ],
)
def test_opening_hours(policies, date, expected):
    result = get_policy("hours", policies, now=date)

    assert result["open_now"] is expected


def test_all_policies_text(policies):
    result = all_policies_text(policies)

    assert "## payment" in result
    assert "## contact" in result
