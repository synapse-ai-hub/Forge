"""Compare router system prompt size: original vs Jinja variants.

The prompts come from the real ``build_system_prompt`` with the tools the
real registry gives for each ``config.yaml`` permission set (so agents,
``AGENT.md`` and context files are this machine's). The original prompt did
not depend on permissions, so it is the full prompt without ``## Seguridad``.

Tokens are counted with the real Gemini ``count_tokens`` endpoint (no
generation, nothing is written to the database or the spend table). Needs
the Google API key saved in the app or in ``GOOGLE_API_KEY``.

    python -m tests.prompts.compare_tokens [model]
"""

from __future__ import annotations

import sys

from backend.agent.loop import _router_tool_permissions
from backend.agent.utils.loop_helpers import build_system_prompt
from backend.instances import agent

MODEL = "gemini-3.5-flash-lite"
SEP = "\n\n---\n\n"

CASES = {
    "Jinja, piso por defecto (sin config.yaml)": None,
    "Jinja, yaml chico (read, websearch, webfetch, search_memory)": {
        "tools": {"read": "allow", "websearch": "allow", "webfetch": "allow", "search_memory": "allow"}
    },
    "Jinja, solo read": {"tools": {"read": "allow"}},
    "Jinja, sin tools": {"tools": {}},
}


def _names(router_perms: dict | None) -> list[str]:
    perms = _router_tool_permissions(router_perms)
    return [t["function"]["name"] for t in agent.tools.tools_registry(perms)]


def _without_security(prompt: str) -> str:
    return SEP.join(p for p in prompt.split(SEP) if not p.startswith("## Seguridad"))


def main(model: str = MODEL) -> None:
    from google import genai

    from backend.agent.utils.provider_keys import resolve_api_key

    key = resolve_api_key("google")
    if not key:
        raise SystemExit("No hay API key de Google configurada.")
    client = genai.Client(api_key=key)

    full = build_system_prompt(None)  # every tool enabled
    prompts = {
        "original (sin Jinja, ignora permisos)": _without_security(full),
        "Jinja, todas las tools + seguridad": full,
    }
    for name, perms in CASES.items():
        prompts[name] = build_system_prompt(None, tools=_names(perms))

    base = None
    print(f"Modelo: {model}\n")
    print(f"{'variante':<62}{'chars':>8}{'tokens':>8}{'vs original':>13}")
    for name, text in prompts.items():
        tokens = client.models.count_tokens(model=model, contents=text).total_tokens
        if base is None:
            base = tokens
        print(f"{name:<62}{len(text):>8}{tokens:>8}{tokens - base:>+13d}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else MODEL)
