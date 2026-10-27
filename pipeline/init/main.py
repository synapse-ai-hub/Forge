"""Orchestrates the full init pipeline (steps 1-11).

If any step fails, the entire target directory is removed so the user
starts from a clean slate on the next attempt.
"""

import shutil
import subprocess
import sys

from pathlib import Path

from .input_handler import get_user_input
from .template_handler import extract_template
from .venv_handler import setup_venv, install_requirements, run_ddl_setup, run_seed_collections
from .config_handler import save_config
from .logo_handler import handle_logo
from .placeholder_handler import replace_all_placeholders


def run(target_dir: str, config: dict | None = None) -> None:
    """Execute the full init pipeline inside *target_dir*.

    When *config* is provided the pipeline uses it directly (GUI mode)
    and skips the interactive ``get_user_input()`` prompt.

    If any step fails, the entire target directory is deleted.

    Args:
        target_dir: Absolute or relative path to the (empty) project directory.
        config: Pre-collected configuration dict (from GUI). When ``None``
            the pipeline prompts via terminal.
    """
    target = Path(target_dir).resolve()
    created_dir = False

    if not target.is_dir():
        print(f"  Creating directory: {target}")
        target.mkdir(parents=True, exist_ok=True)
        created_dir = True

    print("=" * 60)
    print("  synapseForge — Init Pipeline")
    print("=" * 60)

    try:
        # Step 1: User input
        if config is None:
            print("\n[1/11] User input ...")
            config = get_user_input()
        else:
            print("\n[1/11] Using provided configuration ...")

        # Step 2: Download & extract template
        print("\n[2/11] Downloading & extracting template ...")
        extract_template(target)

        # Step 3: Create virtual environment
        print("\n[3/11] Creating virtual environment ...")
        venv_path = setup_venv(target, config["repo"])

        # Step 4: Install Python requirements
        print("\n[4/11] Installing Python requirements ...")
        install_requirements(venv_path, target)

        # Step 5: npm install
        print("\n[5/11] Installing npm dependencies ...")
        _run_npm_install(target)

        # Step 6: Copy logos
        print("\n[6/11] Copying logos ...")
        company_logo_dest = target / "frontend" / "src" / "assets" / "logo_empresa.png"
        handle_logo(config, company_logo_dest, config_key="logo.path")
        company_logo_root = target / "src" / "logo_empresa.png"
        handle_logo(config, company_logo_root, config_key="logo.path")
        client_logo_dest = target / "frontend" / "src" / "assets" / "logo_cliente.png"
        handle_logo(config, client_logo_dest, config_key="logo_cliente")

        # Step 7: Generate .ico from client logo
        print("\n[7/11] Generating favicon (.ico) ...")
        _run_generate_ico(venv_path, client_logo_dest)

        # Step 8: Extract colors from client logo
        print("\n[8/11] Resolving colors ...")
        _resolve_colors(config, client_logo_dest)

        # Step 9: Save user config (colors already in dict)
        print("\n[9/11] Saving configuration ...")
        save_config(target, config)

        # Step 10: Replace placeholders
        print("\n[10/11] Replacing placeholders ...")
        replace_all_placeholders(target, config)

        # Step 11: Initialize database schema (ddl_setup)
        print("\n[11/11] Initializing database schema (ddl_setup) and help collection ...")
        run_ddl_setup(target, venv_path)
        run_seed_collections(target, venv_path)

    except Exception as exc:
        print(f"\n  ERROR: Init failed at step — {exc}")
        print(f"  Cleaning up: {target}")
        _cleanup(target, created_dir)
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  Done! Project initialized in:", target)
    print("=" * 60)


def _cleanup(target: Path, created_dir: bool) -> None:
    """Remove the target directory if init failed.

    Args:
        target: The project directory to remove.
        created_dir: Whether this function created the directory
            (if True and removal fails, at least print a warning).
    """
    try:
        if target.is_dir():
            shutil.rmtree(target)
            print(f"  Removed: {target}")
    except Exception as exc:
        print(f"  WARNING: could not remove {target}: {exc}")
        print(f"  Please remove it manually.")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _run_npm_install(target: Path) -> None:
    """Run ``npm install`` in the frontend directory.

    Args:
        target: Project root directory.
    """
    frontend_dir = target / "frontend"
    if not (frontend_dir / "package.json").is_file():
        print("  WARNING: package.json not found, skipping npm install")
        return

    try:
        subprocess.run(
            "npm install",
            cwd=str(frontend_dir),
            shell=True,
            check=True,
        )
        print("  npm install completed")
    except subprocess.CalledProcessError as exc:
        print(f"  WARNING: npm install failed (exit code {exc.returncode})")
    except FileNotFoundError:
        print("  WARNING: npm not found, skipping npm install")


def _run_generate_ico(venv_path: Path, logo_png: Path) -> None:
    """Generate ``.ico`` from the logo PNG using Pillow (inline).

    Args:
        venv_path: Path to the virtual environment root.
        logo_png: Logo to convert.
    """
    if not logo_png.is_file():
        print("  WARNING: logo PNG not found, skipping .ico generation")
        return

    try:
        from PIL import Image
    except ImportError:
        print("  WARNING: Pillow not available, skipping .ico generation")
        return

    ico_path = logo_png.with_suffix(".ico")
    try:
        img = Image.open(str(logo_png))
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        img.save(str(ico_path), format="ICO", sizes=sizes)
        print(f"  Generated: {ico_path}")
    except Exception as exc:
        print(f"  WARNING: .ico generation failed: {exc}")


def _resolve_colors(config: dict, logo_png: Path) -> None:
    """Validate that all 4 color fields exist in config.

    Args:
        config: User configuration dict.
        logo_png: Logo the colors come from.
    """
    keys = ["primary", "secondary", "primary_text", "gradient_secondary"]
    colors = config.setdefault("colors", {})
    missing = [k for k in keys if not colors.get(k)]
    if missing:
        print(f"  WARNING: missing colors in config: {missing}")
        return

    for k in keys:
        print(f"  {k}: {colors[k]}")
    usar = colors.get("usar_gradiente", True)
    print(f"  gradient: {'ON' if usar else 'OFF'}")
