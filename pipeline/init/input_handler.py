"""Step 1 — Interactive user input for all replace.json fields."""

import re
import sys
from pathlib import Path
from typing import Dict, Optional


def get_user_input() -> Dict[str, object]:
    """Prompt the user for every field and return a validated config dict.

    Returns:
        A dictionary with the same structure as ``config/replace.json``.
    """
    print("\nIngresá los datos del proyecto (dejá vacío para omitir):\n")

    # ── Logo ────────────────────────────────────────────────────────────
    logo_path: Optional[str] = _prompt("Logo de la empresa (para README, sin comillas)", required=True)
    logo_resolved = _resolve_logo(logo_path)

    # ── Project info ────────────────────────────────────────────────────
    empresa: str = _prompt("Nombre de la empresa desarrolladora", required=True)
    owner: str = _prompt("Owner del repo (usuario de GitHub)", required=True)
    legal: str = _prompt("Nombre legal / razón social", required=True)
    repo: str = _prompt("Nombre del repo", required=True)
    cliente: str = _prompt("Nombre del cliente", required=True)
    logo_cliente: str = _prompt("Logo del cliente (para la app, opcional, sin comillas)", default="")
    nombre: str = _prompt("Nombre del proyecto", required=True)
    tarea: str = _prompt("Nombre de la tarea / rubro", required=True)

    # ── Colores (obligatorios) ──────────────────────────────────────────
    print("\nColores del proyecto:")
    print("  Primary: color principal (botones, headers, burbujas)")
    print("  Secondary: color secundario (hover, detalles light)")
    print("  Primary Text: color de texto (botones, headers)")
    print("  Gradient Secondary: color secundario del gradiente (igual al primary si no usás gradiente)\n")

    colors: Dict[str, object] = {}

    c = _prompt_hex("Color principal (ej: #D76F10)", required=True)
    colors["primary"] = c

    c = _prompt_hex("Color secundario (ej: #F0A347)", required=True)
    colors["secondary"] = c

    c = _prompt_hex("Color de texto (ej: #FFFFFF)", required=True)
    colors["primary_text"] = c

    # ── Gradient toggle ────────────────────────────────────────────────
    usar = _prompt("¿Usar gradiente en botones/headers? (s/N)", default="n")
    colors["usar_gradiente"] = usar.lower() in ("s", "si", "y", "yes", "1", "true")
    if colors["usar_gradiente"]:
        c = _prompt_hex("Color secundario del gradiente (ej: #F0A347)", required=True)
        colors["gradient_secondary"] = c
    else:
        colors["gradient_secondary"] = colors["primary"]

    return {
        "logo": {
            "path": str(logo_resolved),
        },
        "empresa": empresa,
        "owner": owner,
        "legal": legal,
        "repo": repo,
        "cliente": cliente,
        "logo_cliente": logo_cliente or None,
        "nombre": nombre,
        "tarea": tarea,
        "colors": colors,
    }


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _prompt(label: str, *, required: bool = False, default: str = "") -> str:
    """Ask for a text value. Loop until non-empty if *required*.

    Args:
        label: Text shown to the user.
        required: True to ask again until the answer is not empty.
        default: Value used when the answer is empty.

    Returns:
        The answer of the user.
    """
    hint = f" [{default}]" if default else ""
    suffix = " *" if required else ""
    while True:
        value = input(f"  {label}{suffix}{hint}: ").strip()
        if not value:
            value = default
        if value:
            return value
        if not required:
            return ""
        print("    ⚠ Este campo es obligatorio.")


def _prompt_hex(label: str, *, required: bool = False) -> str:
    """Ask for a hex color. Return hex string if provided.

    Args:
        label: Prompt label.
        required: When True, loop until a valid hex is entered.

    Returns:
        The hex color string, or ``""`` if not required and skipped.
    """
    while True:
        value = input(f"  {label}: ").strip()
        if not value and not required:
            return ""
        if not value:
            print("    ⚠ Este campo es obligatorio.")
            continue
        if _HEX_RE.match(value):
            return value
        print("    ⚠ Formato inválido. Usá #RRGGBB (ej: #D76F10).")


def _resolve_logo(raw: str) -> Path:
    """Resolve and validate the logo path.

    Args:
        raw: Path typed by the user.

    Returns:
        The resolved path of the logo.
    """
    p = Path(raw).resolve()
    if not p.is_file():
        print(f"  ⚠ Archivo no encontrado: {p}")
        sys.exit(1)
    return p