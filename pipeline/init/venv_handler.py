"""Steps 3-4 — Create virtual environment and install dependencies."""

import subprocess
import sys
from pathlib import Path


def setup_venv(target: Path, repo_name: str) -> Path:
    """Create a Python virtual environment at ``{target}/.{repo_name}``.

    Args:
        target: Project root directory.
        repo_name: Used as the venv folder name (``.{{repo_name}}``).

    Returns:
        Path to the venv root.
    """
    venv_dir = target / f".{repo_name}"
    if venv_dir.is_dir():
        print(f"  Virtual env already exists: {venv_dir}")
        return venv_dir

    result = subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  ERROR creating venv: {result.stderr.strip()}")
        sys.exit(1)

    print(f"  Created: {venv_dir}")
    return venv_dir


def install_requirements(venv_path: Path, target: Path) -> None:
    """Run ``pip install -r requirements.txt`` inside the venv.

    Args:
        venv_path: Path to the virtual environment root.
        target: Project root (where ``requirements.txt`` lives).
    """
    req_file = target / "requirements.txt"
    if not req_file.is_file():
        print("  WARNING: requirements.txt not found, skipping install")
        return

    python = _venv_python(venv_path)
    result = subprocess.run(
        [str(python), "-m", "pip", "install", "-r", str(req_file)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  WARNING: pip install failed:\n{result.stderr.strip()}")
        return

    # Print last line of pip output (usually "Successfully installed ...")
    last_line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    if last_line:
        print(f"  {last_line}")
    else:
        print("  Requirements installed.")


def get_venv_python(venv_path: Path) -> Path:
    """Return the path to the venv's Python executable."""
    if sys.platform == "win32":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def _venv_python(venv_path: Path) -> Path:
    """Return the path to the venv's Python executable (Windows)."""
    return venv_path / "Scripts" / "python.exe"


def run_seed_collections(target: Path, venv_path: Path) -> None:
    """Load the internal ``help`` collection (already vectorized) into the knowledge dir."""
    python = get_venv_python(venv_path)
    if not python.is_file():
        python = Path(sys.executable)

    code = (
        "from backend.agent.utils.seed_collections import seed_help_collection; "
        "added = seed_help_collection(); "
        "print(f'  Help collection: {added} sections loaded.' if added else '  Help collection already present.')"
    )

    try:
        result = subprocess.run(
            [str(python), "-c", code],
            cwd=str(target),
            capture_output=True,
            text=True,
            check=True,
        )
        if result.stdout.strip():
            print(f"  {result.stdout.strip()}")
    except subprocess.CalledProcessError as exc:
        print(f"  WARNING: help collection seed failed:\n{exc.stderr.strip()}")
    except Exception as exc:
        print(f"  WARNING: help collection seed error: {exc}")


def run_ddl_setup(target: Path, venv_path: Path) -> None:
    """Run ddl_setup to initialize/update the SQLite database tables."""
    db_path = target / "backend" / "agent" / "agent_db" / "agent.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    python = get_venv_python(venv_path)
    if not python.is_file():
        python = Path(sys.executable)

    code = (
        "import sqlite3; "
        f"db_path = r'{db_path}'; "
        "conn = sqlite3.connect(db_path); "
        "from backend.agent.ddl_setup import setup_database; "
        "setup_database(conn); "
        "conn.commit(); "
        "conn.close(); "
        "print('  Database schema initialized/updated successfully.')"
    )

    try:
        result = subprocess.run(
            [str(python), "-c", code],
            cwd=str(target),
            capture_output=True,
            text=True,
            check=True,
        )
        if result.stdout.strip():
            print(f"  {result.stdout.strip()}")
    except subprocess.CalledProcessError as exc:
        print(f"  WARNING: ddl_setup failed:\n{exc.stderr.strip()}")
    except Exception as exc:
        print(f"  WARNING: ddl_setup execution error: {exc}")
