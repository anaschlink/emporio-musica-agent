
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from emporio.prompts import build_system_prompt
from emporio.policies import POLICY_FILES

TZ = ZoneInfo("America/Campo_Grande")


def test_build_prompt_in_tool_mode():
    prompt = build_system_prompt(policy_mode="tool")

    assert "Empório da Música" in prompt
    assert "Brazilian Portuguese" in prompt
    assert "TOOL USAGE" in prompt


def test_build_prompt_with_fixed_datetime():
    now = datetime(2026, 11, 2, 10, 30, tzinfo=TZ)

    prompt = build_system_prompt(now=now)

    assert now.isoformat() in prompt


def test_inline_mode_includes_policies():
    policies = {
        topic: f"Content for {topic}"
        for topic in POLICY_FILES
    }

    prompt = build_system_prompt(policies=policies, policy_mode="inline")

    assert "STORE POLICIES" in prompt
    assert "Content for payment" in prompt
    assert "Content for contact" in prompt


def test_inline_mode_requires_policies():
    with pytest.raises(ValueError):
        build_system_prompt(policy_mode="inline")


def test_invalid_policy_mode():
    with pytest.raises(ValueError):
        build_system_prompt(policy_mode="invalid")
