from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

POLICIES_DIR = Path(__file__).resolve().parent.parent / "policies"
TIMEZONE = ZoneInfo("America/Campo_Grande")

POLICY_FILES = {
    "payment": "payment.md",
    "returns": "returns.md",
    "shipping": "shipping.md",
    "promotions": "promotions.md",
    "warranty": "warranty.md",
    "hours": "hours.md",
    "privacy": "privacy.md",
    "scope": "scope.md",
    "contact": "contact.md",
}


def load_policies(directory: Path = POLICIES_DIR) -> dict[str, str]:
    """Load all policy files from the configured directory."""
    policies = {}

    for topic, filename in POLICY_FILES.items():
        path = directory / filename

        if not path.exists():
            raise FileNotFoundError(f"Policy file not found: {path}")

        content = path.read_text(encoding="utf-8").strip()

        if not content:
            raise ValueError(f"Policy file is empty: {path}")

        policies[topic] = content

    return policies


def get_policy(
    topic: str,
    policies: dict[str, str],
    now: datetime | None = None,
) -> dict:
    """Return a policy by topic, including current opening status when relevant."""
    if topic not in POLICY_FILES:
        return {
            "success": False,
            "error": "unknown_topic",
            "available_topics": list(POLICY_FILES),
        }

    if topic not in policies or not policies[topic].strip():
        return {
            "success": False,
            "error": "policy_unavailable",
            "topic": topic,
        }

    result = {
        "success": True,
        "topic": topic,
        "content": policies[topic],
    }

    if topic == "hours":
        current = now or datetime.now(TIMEZONE)

        if current.tzinfo is None:
            current = current.replace(tzinfo=TIMEZONE)
        else:
            current = current.astimezone(TIMEZONE)

        weekday = current.weekday()
        current_time = current.time()

        if weekday < 5:
            opening = current_time.replace(hour=9, minute=0, second=0, microsecond=0)
            closing = current_time.replace(hour=18, minute=0, second=0, microsecond=0)
        elif weekday == 5:
            opening = current_time.replace(hour=9, minute=0, second=0, microsecond=0)
            closing = current_time.replace(hour=13, minute=0, second=0, microsecond=0)
        else:
            opening = closing = None

        is_open = opening is not None and opening <= current_time < closing

        result["open_now"] = is_open
        result["checked_at"] = current.isoformat()

    return result


def all_policies_text(policies: dict[str, str]) -> str:
    """Combine all policies into a single text for inline prompt mode."""
    return "\n\n".join(
        f"## {topic}\n{policies[topic]}"
        for topic in POLICY_FILES
        if topic in policies and policies[topic].strip()
    )
