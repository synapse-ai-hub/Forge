#!/usr/bin/env python3
"""Regenerate pipeline/template.zip from the template/ folder with automatic steps."""

import zipfile
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path


AR_TZ = timezone(timedelta(hours=-3))

ROOT = Path(__file__).resolve().parents[2]  # synapseForge root
TEMPLATE_DIR = ROOT / "template"
ZIP_PATH = ROOT / "pipeline" / "template.zip"


_AGENT_DB_FILES = {"agent.db", "agent.db-shm", "agent.db-wal"}


def _ignore_frontend(directory: str, names: list[str]) -> set[str]:
    """Exclude from the copy what does not belong in the frontend template.

    Args:
        directory: Directory being copied.
        names: Names inside that directory.

    Returns:
        The names to skip.
    """
    return {n for n in names if n in ("node_modules", "__pycache__")}


def _ignore_backend(directory: str, names: list[str]) -> set[str]:
    """Exclude from the copy what does not belong in the backend template.

    Args:
        directory: Directory being copied.
        names: Names inside that directory.

    Returns:
        The names to skip.
    """
    ignored = {n for n in names if n == "__pycache__"}
    if Path(directory).name == "agent_db":
        ignored |= _AGENT_DB_FILES & set(names)
    return ignored


def main() -> None:
    """Rebuild the template folder from the backend and the frontend and zip it."""
    if not TEMPLATE_DIR.is_dir():
        print(f"ERROR: No existe {TEMPLATE_DIR}")
        return

    # ========================================================================
    # PASOS DE PREPARACIÓN (siempre se ejecutan al inicio)
    # ========================================================================
    
    # 1. Borrar carpeta backend completa de template/
    if (TEMPLATE_DIR / "backend").is_dir():
        shutil.rmtree(TEMPLATE_DIR / "backend")

    # 2. Borrar carpeta frontend completa de template/
    if (TEMPLATE_DIR / "frontend").is_dir():
        shutil.rmtree(TEMPLATE_DIR / "frontend")

    # 3. Copiar backend desde synapseForge/backend a template/backend
    #    (sin __pycache__ ni la base de datos y sus archivos -shm/-wal)
    shutil.copytree(ROOT / "backend", TEMPLATE_DIR / "backend", ignore=_ignore_backend)

    # 4. Copiar frontend desde synapseForge/frontend a template/frontend
    #    (sin node_modules ni __pycache__)
    shutil.copytree(ROOT / "frontend", TEMPLATE_DIR / "frontend", ignore=_ignore_frontend)

    # Borrar zip anterior antes de crear uno nuevo
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    # Crear carpeta destino del zip (si no existe)
    ZIP_PATH.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in TEMPLATE_DIR.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(TEMPLATE_DIR)
                zf.write(file_path, arcname)

    print(f"[{datetime.now(AR_TZ):%H:%M:%S}] OK template.zip regenerado en {ZIP_PATH}")


if __name__ == "__main__":
    main()
