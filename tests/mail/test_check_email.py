"""Call the real check_email tool with environment variables.

Run the fixed suite::

    python -m tests.mail.test_check_email

Run a single case with arguments::

    python -m tests.mail.test_check_email --date 7d --folder INBOX --sender someone@example.com --peek
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from backend.agent.tools import Tools


def show(label: str, result: dict) -> bool:
    """Print a tool result summary. Returns True when status is success."""
    print(f"[{label}] status: {result.get('status')}")
    print(f"[{label}] message: {result.get('message')}")
    data = result.get("data") or []
    print(f"[{label}] emails: {len(data)}")
    for email in data:
        print(f"[{label}] - {email.get('date')} | {email.get('sender')} | {email.get('subject')}")
    return result.get("status") == "success"


def main() -> int:
    """Instantiate Tools and call check_email (suite or single case)."""
    parser = argparse.ArgumentParser(description="Call the real check_email tool.")
    parser.add_argument("--date", default=None, help="Age filter: 1h-23h, <n>d, <n>m, <n>y, all")
    parser.add_argument("--folder", default=None, help="IMAP folder (default INBOX)")
    parser.add_argument("--sender", default=None, help="Filter by sender address")
    parser.add_argument("--peek", action="store_true", help="List without marking as read")
    args = parser.parse_args()

    tools = Tools()
    failures = 0

    if args.date is not None or args.folder is not None or args.sender is not None or args.peek:
        ok = show(
            "single",
            asyncio.run(tools.check_email(
                folder=args.folder or "INBOX",
                sender=args.sender,
                date=args.date or "1h",
                mark_read=not args.peek,
            )),
        )
        return 0 if ok else 1

    if show("invalid", asyncio.run(tools.check_email(date="xyz"))):
        failures += 1
    if not show("default", asyncio.run(tools.check_email())):
        failures += 1
    if not show("7d", asyncio.run(tools.check_email(date="7d"))):
        failures += 1
    if not show("all", asyncio.run(tools.check_email(date="all"))):
        failures += 1
    if not show("peek", asyncio.run(tools.check_email(date="all", mark_read=False))):
        failures += 1

    print(f"failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
