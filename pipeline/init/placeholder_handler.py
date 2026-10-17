"""Step 9 — Replace every XML placeholder tag in the extracted template.

Scans all text files under the target directory and replaces occurrences
of ``<tag>value</tag>`` with the actual value from the user config.

Supports nested tags such as ``<nombre>nombre_proyecto</nombre>``,
``<cliente>...</cliente>``, ``<color_primario>...</color_primario>``, etc.
"""

import re
from pathlib import Path
from typing import Dict, Pattern

# ---------------------------------------------------------------------------
# Tag → config key mapping
# ---------------------------------------------------------------------------
TAG_MAP: Dict[str, str] = {
    "logo": "logo.path",
    "empresa": "empresa",
    "owner": "owner",
    "legal": "legal",
    "repo": "repo",
    "cliente": "cliente",
    "logo_cliente": "logo_cliente",
    "nombre": "nombre",
    "tarea": "tarea",
    # Colors — 4 configurables + gradient toggle
    "color_primario": "colors.primary",
    "color_secundario": "colors.secondary",
    "color_texto_primario": "colors.primary_text",
    "color_secundario_gradiente": "colors.gradient_secondary",
}

# Regex that matches <tag>anything</tag>.  Tag names must be [a-z_]+.
_TAG_RE: Pattern = re.compile(r"<([a-z_]+)>([^<]*)</\1>")


def replace_all_placeholders(target: Path, config: dict) -> None:
    """Walk the entire *target* tree and replace XML placeholders.

    Only processes text-like files (extensions: .py, .tsx, .ts, .js, .jsx,
    .html, .css, .md, .json, .txt, .yaml, .yml, .toml, .ini, .cfg, .env).

    Args:
        target: Project root directory.
        config: User config dictionary.
    """
    replacements = _build_replacement_map(config)

    # Track stats for final summary
    modified_files = 0
    total_replacements = 0

    for file_path in target.rglob("*"):
        if not file_path.is_file():
            continue
        if not _is_text_file(file_path):
            continue

        # Skip node_modules, .git, __pycache__, .venv
        if _should_skip(file_path):
            continue

        try:
            original = file_path.read_bytes()
        except Exception:
            continue  # skip binary or permission-denied

        text = original.decode("utf-8", errors="replace")

        new_text, count = _replace_tags(text, replacements)

        if count > 0 and new_text != text:
            file_path.write_bytes(new_text.encode("utf-8"))
            modified_files += 1
            total_replacements += count

    print(f"  Replaced {total_replacements} placeholder(s) across {modified_files} file(s)")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_replacement_map(config: dict) -> Dict[str, str]:
    """Flatten the nested config into ``{tag: value}``."""
    replacements: Dict[str, str] = {}

    for tag, key_path in TAG_MAP.items():
        if tag == "logo":
            # Path relativo al repo desde la raíz (el logo se copia a ambos lugares)
            replacements[tag] = "src/logo_empresa.png"
        else:
            value = _deep_get(config, key_path)
            if value is not None and value != "":
                replacements[tag] = str(value)

    return replacements


def _deep_get(d: dict, dotted: str):
    """Traverse a dict with a dotted path like ``colors.primary``."""
    parts = dotted.split(".")
    current: object = d
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _replace_tags(text: str, replacements: Dict[str, str]) -> tuple:
    """Replace all ``<tag>...</tag>`` spans in *text* with the mapped value.

    Returns ``(new_text, count)``.
    """

    def _replacer(m: re.Match) -> str:
        tag = m.group(1)
        if tag in replacements:
            return replacements[tag]
        # Unrecognised tag → leave untouched
        return m.group(0)

    new_text, count = _TAG_RE.subn(_replacer, text)
    return new_text, count


_TEXT_EXTENSIONS = frozenset({
    ".py", ".tsx", ".ts", ".js", ".jsx",
    ".html", ".css", ".md", ".json", ".txt",
    ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".env", ".env.example", ".gitignore",
    ".ps1", ".bat", ".cmd", ".sh",
    ".jinja",
})

_NOEXT_NAMES = frozenset({
    "LICENSE", "CHANGELOG", "CONTRIBUTORS",
})

_SKIP_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv",
    ".synapseForge", ".vite", ".vite-temp",
})


def _is_text_file(path: Path) -> bool:
    """Check extension against known text types."""
    return (
        path.suffix in _TEXT_EXTENSIONS
        or path.name == ".gitignore"
        or path.name in _NOEXT_NAMES
    )


def _should_skip(path: Path) -> bool:
    """Return True if the path is inside a directory that should be skipped."""
    for parent in path.parents:
        if parent.name in _SKIP_DIRS:
            return True
    return False
