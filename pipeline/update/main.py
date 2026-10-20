"""Orchestrates the update pipeline.

Before overwriting anything, the entire project is backed up to
``~/.config/synapseForge/backup/``.  If the update fails, the project
is restored from that backup.  On success the user is asked whether to
keep or delete the backup.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from ..init.template_handler import extract_template
from ..init.config_handler import load_config, save_colors
from ..init.placeholder_handler import replace_all_placeholders
from ..init.venv_handler import run_ddl_setup


def _smart_merge(backup_path: str, target_path: str) -> None:
    """Merge two text files by combining unique lines (backup + new)."""
    try:
        with open(backup_path, "r", encoding="utf-8") as f:
            backup_lines = [line.rstrip("\n") for line in f]
        with open(target_path, "r", encoding="utf-8") as f:
            target_lines = [line.rstrip("\n") for line in f]
        # Combine unique lines preserving order (backup first, then new additions)
        seen = set()
        merged = []
        for line in backup_lines + target_lines:
            if line == "":
                merged.append(line)
            elif line not in seen:
                seen.add(line)
                merged.append(line)
        with open(target_path, "w", encoding="utf-8") as f:
            for line in merged:
                f.write(line + "\n")
    except Exception:
        pass


def _get_backup_dir() -> Path:
    """Return ``~/.config/synapseForge/backup/``, creating it if needed."""
    import os
    base = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    backup = base / "synapseForge" / "backup"
    backup.mkdir(parents=True, exist_ok=True)
    return backup


def _backup_project(target: Path, backup_dir: Path) -> None:
    """Copy the entire project into *backup_dir*/project/.

    Removes any previous backup first so we always start clean.

    Args:
        target: The project directory to back up.
        backup_dir: The config backup root (``~/.config/synapseForge/backup/``).

    Raises:
        OSError: If the copy fails.
    """
    dest = backup_dir / "project"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(target, dest)
    print(f"  Backup saved to: {dest}")


def _restore_project(target: Path, backup_dir: Path) -> None:
    """Restore the project from the backup.

    Removes the current project directory and replaces it with the backup.

    Args:
        target: The project directory to restore.
        backup_dir: The config backup root.
    """
    src = backup_dir / "project"
    if not src.exists():
        print("  WARNING: no backup found, cannot restore.")
        return
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(src, target)
    print(f"  Project restored from backup: {src}")


def _cleanup_backup(backup_dir: Path) -> None:
    """Remove the backup directory.

    Args:
        backup_dir: The config backup root.
    """
    project_backup = backup_dir / "project"
    if project_backup.exists():
        shutil.rmtree(project_backup)
        print(f"  Backup removed: {project_backup}")


def run_update(target_dir: str) -> None:
    """Update the project with the latest template, preserving user config.

    Flow:
        1. Back up the entire project to ``~/.config/synapseForge/backup/``.
        2. Read ``config/replace.json`` from the backup.
        3. Download and extract the new template (overwrites base files).
        4. Re-apply placeholders from the saved config.
        5. Regenerate derived files (colors.json).
        6. On failure → restore from backup, delete backup.
        7. On success → ask user whether to keep or delete the backup.
    """
    target = Path(target_dir).resolve()
    backup_dir = _get_backup_dir()

    # ── Check prerequisites ───────────────────────────────────────────
    config_path = target / "config" / "replace.json"
    if not config_path.is_file():
        print(f"ERROR: Configuration file not found at {config_path}. Cannot update.")
        return

    print("=" * 60)
    print("  synapseForge — Update Pipeline")
    print("=" * 60)

    # ── Step 1: Backup ────────────────────────────────────────────────
    print("\n[1/6] Backing up project ...")
    try:
        _backup_project(target, backup_dir)
    except Exception as exc:
        print(f"\n  ERROR: Backup failed — {exc}")
        print("  Update aborted. Your project is untouched.")
        sys.exit(1)

    # ── Steps 2-5: Update ────────────────────────────────────────────
    # Read config from the backup (not from the live project, which
    # will be overwritten).
    backup_project = backup_dir / "project"
    try:
        print("\n[2/6] Loading configuration from backup ...")
        config = load_config(backup_project)

        print("\n[3/6] Downloading & extracting new template ...")
        extract_template(target)

        # Mandatory preservation: config folder, logos, agent.db, README.md
        # Config folder
        config_backup = backup_project / "config"
        config_target = target / "config"
        if config_backup.exists():
            if config_target.exists():
                shutil.rmtree(config_target)
            shutil.copytree(str(config_backup), str(config_target))
            print("  Preserved config/ folder from backup.")

        # Logos
        for logo_name in ["logo_cliente.png", "logo_empresa.png"]:
            logo_backup = backup_project / "frontend" / "src" / "assets" / logo_name
            logo_target = target / "frontend" / "src" / "assets" / logo_name
            if logo_backup.exists():
                logo_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(logo_backup), str(logo_target))
                print(f"  Preserved logo: {logo_name}")

        # Agent DB
        agent_db_backup = backup_project / "backend" / "agent" / "agent_db" / "agent.db"
        agent_db_target = target / "backend" / "agent" / "agent_db" / "agent.db"
        if agent_db_backup.exists():
            agent_db_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(agent_db_backup), str(agent_db_target))
            print("  Preserved agent.db from backup.")

        # README.md (project root)
        readme_backup = backup_project / "README.md"
        readme_target = target / "README.md"
        if readme_backup.exists():
            shutil.copy2(str(readme_backup), str(readme_target))
            print("  Preserved README.md from backup.")

        # Smart merge for files that may have user + owner changes
        smart_merge_files = [
            ".env",
            ".env.example",
            ".gitignore",
            ".dockerignore",
            "docker-compose.yml",
            "docker-compose.yaml",
            "Dockerfile",
            "requirements.txt",
        ]
        for fname in smart_merge_files:
            backup_file = backup_project / fname
            target_file = target / fname
            if backup_file.exists() and target_file.exists():
                _smart_merge(str(backup_file), str(target_file))
                print(f"  Smart-merged: {fname}")
            elif backup_file.exists() and not target_file.exists():
                shutil.copy2(str(backup_file), str(target_file))
                print(f"  Copied from backup: {fname}")

        print("\n[4/6] Re-applying placeholders ...")
        replace_all_placeholders(target, config)

        print("\n[5/6] Regenerating derived files ...")
        save_colors(target, config)

        print("\n[6/6] Initializing/updating database schema (ddl_setup) ...")
        repo_name = config.get("repo", "synapse")
        venv_path = target / f".{repo_name}"
        run_ddl_setup(target, venv_path)

    except Exception as exc:
        # ── Failure: restore from backup ──────────────────────────────
        print(f"\n  ERROR: Update failed — {exc}")
        print("  Restoring project from backup ...")
        _restore_project(target, backup_dir)
        _cleanup_backup(backup_dir)
        print("  Project restored to previous state.")
        sys.exit(1)

    # ── Success: ask about backup ─────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Update completed successfully!")
    print("=" * 60)

    try:
        answer = input("\n  Keep the backup? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"

    if answer == "y":
        print(f"  Backup kept at: {backup_dir / 'project'}")
    else:
        _cleanup_backup(backup_dir)
