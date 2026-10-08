"""Call the real check_email tool with environment variables.

Run with ``python -m tests.mail.test_check_email``.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from backend.agent.tools import Tools


def show(label: str, result: dict) -> None:
    """Print a tool result summary."""
    print(f"[{label}] status: {result.get('status')}")
    print(f"[{label}] message: {result.get('message')}")
    data = result.get("data") or []
    print(f"[{label}] emails: {len(data)}")
    for email in data:
        print(f"[{label}] - {email.get('date')} | {email.get('sender')} | {email.get('subject')}")


def main() -> int:
    """Instantiate Tools and call check_email with several date filters."""
    tools = Tools()
    failures = 0

    invalid = asyncio.run(tools.check_email(date="xyz"))
    show("invalid", invalid)
    if invalid.get("status") != "error":
        failures += 1

    default = asyncio.run(tools.check_email())
    show("default", default)
    if default.get("status") != "success":
        failures += 1

    week = asyncio.run(tools.check_email(date="7d"))
    show("7d", week)
    if week.get("status") != "success":
        failures += 1

    everything = asyncio.run(tools.check_email(date="all"))
    show("all", everything)
    if everything.get("status") != "success":
        failures += 1

    print(f"failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
