"""Vertical-specific writing templates for the first wedge niches."""

from __future__ import annotations

VERTICALS: dict[str, dict] = {
    "general": {
        "name": "General",
        "default_format": "short document",
        "audience": "the reader",
        "goal": "communicate the brief clearly and persuasively in the author's voice.",
        "guardrails": "Stay faithful to the brief; do not invent facts, names, numbers or quotes.",
    },
    "fundraising": {
        "name": "Fundraising",
        "default_format": "investor update",
        "formats": ["investor update", "pitch email", "fundraising memo", "one-pager"],
        "audience": "investors and limited partners",
        "goal": "build conviction and momentum while being specific and honest about progress and asks.",
        "guardrails": (
            "Do not fabricate metrics, traction, revenue, valuation or commitments. "
            "Use placeholders like [metric] where the brief lacks a number."
        ),
    },
    "legal": {
        "name": "Legal",
        "default_format": "client memo",
        "formats": ["client memo", "demand letter", "risk summary", "terms explanation"],
        "audience": "clients and counterparties",
        "goal": "state the legal position clearly, cite authority where given, and flag uncertainty.",
        "guardrails": (
            "This output is a draft, not legal advice; include a one-line notice when "
            "appropriate. Do not invent statutes, case names, or citations."
        ),
    },
    "newsletter": {
        "name": "Newsletter",
        "default_format": "issue",
        "formats": ["issue", "welcome email", "essay", "roundup"],
        "audience": "subscribers",
        "goal": "open with a hook, deliver one clear takeaway, and keep a consistent voice readers trust.",
        "guardrails": "Do not invent facts, links, sources or subscriber numbers.",
    },
}

DEFAULT_VERTICAL = "general"


def get_vertical(name: str) -> dict:
    return VERTICALS.get(name, VERTICALS[DEFAULT_VERTICAL])


def vertical_names() -> list[str]:
    return list(VERTICALS)
