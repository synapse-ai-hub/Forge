#!/usr/bin/env python3
"""synapseForge - Distribution builder for agent repos.

Creates a self-contained zip with compiled backend, frontend, venv,
launcher executable, .env, LICENSE, and README.

Usage:
    python forge.py <repo_path> "<exe_name>" [--compile]

Example:
    python forge.py D:\\ia-san-juan\\4_reinas "<cliente>nombre_cliente</cliente>"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from string import Template


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TEMPLATES_DIR = Path(__file__).parent / "templates"
BUILD_DIR_NAME = "__forge_build__"
EMBEDDED_PYTHON_VERSION = "3.12.0"
EMBEDDED_PYTHON_URL = (
    f"https://www.python.org/ftp/python/{EMBEDDED_PYTHON_VERSION}/"
    f"python-{EMBEDDED_PYTHON_VERSION}-embed-amd64.zip"
)
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
CACHE_DIR = Path(__file__).parent / ".cache"

# Files/folders to exclude from backend after compilation
BACKEND_EXCLUDED_DIRS: set[str] = {
    "__pycache__",
}
BACKEND_EXCLUDED_FILES: set[str] = {
    "agent.db",
}
# Only keep .md/.txt inside these relative paths
BACKEND_KEEP_MD_TXT_PATHS: set[str] = {
    "agent/prompts",
}


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------
def _log(msg: str, *, err: bool = False) -> None:
    tag = "ERR" if err else "INF"
    print(f"[{tag}] {msg}", file=sys.stderr if err else sys.stdout)


def _step(n: int, total: int, label: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  Step {n}/{total}: {label}")
    print(f"{'=' * 60}")


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
def _repo_name(repo_path: str) -> str:
    """Extract the last directory component as the repo name."""
    return Path(repo_path).resolve().name


# ---------------------------------------------------------------------------
# Version extraction from frontend/package.json
# ---------------------------------------------------------------------------
def _get_version(repo_path: str) -> str:
    """Read version from frontend/package.json, fallback to '0.1.0'."""
    pkg = Path(repo_path) / "frontend" / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            return data.get("version", "0.1.0")
        except (json.JSONDecodeError, OSError):
            pass
    return "0.1.0"


# ---------------------------------------------------------------------------
# Step: Download and setup embedded Python
# ---------------------------------------------------------------------------
def _download_file(url: str, dest: Path) -> None:
    """Download a file with progress indicator."""
    _log(f"  Downloading {url.split('/')[-1]} ...")
    try:
        urllib.request.urlretrieve(url, str(dest))
    except urllib.error.URLError as e:
        _log(f"Download failed: {e}", err=True)
        sys.exit(1)


def _setup_embedded_python(repo_path: str, build_dir: Path) -> Path:
    """Download, configure, and install deps into embedded Python.

    Returns the path to the configured python/ directory.
    """
    python_dir = build_dir / "dist" / "python"
    if python_dir.is_dir():
        _log("Embedded Python already configured, skipping.")
        return python_dir

    # Ensure cache dir
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Step A: Download embedded Python zip (cache it)
    embed_zip = CACHE_DIR / f"python-{EMBEDDED_PYTHON_VERSION}-embed-amd64.zip"
    if not embed_zip.is_file():
        _download_file(EMBEDDED_PYTHON_URL, embed_zip)
    else:
        _log(f"  Using cached: {embed_zip.name}")

    # Step B: Extract
    _log("  Extracting embedded Python ...")
    shutil.unpack_archive(str(embed_zip), str(python_dir))

    # Step C: Configure _pth file
    pth_file = None
    for f in python_dir.iterdir():
        if f.name.endswith("._pth"):
            pth_file = f
            break
    if pth_file is None:
        _log("No _pth file found in embedded Python!", err=True)
        sys.exit(1)

    _log(f"  Configuring {pth_file.name} ...")
    pth_lines = pth_file.read_text(encoding="utf-8").splitlines()
    new_lines: list[str] = []
    has_site_packages = False
    for line in pth_lines:
        stripped = line.strip()
        if stripped == "#import site":
            new_lines.append("import site")
        elif stripped == "Lib\\site-packages":
            has_site_packages = True
            new_lines.append(line)
        else:
            new_lines.append(line)
    if not has_site_packages:
        new_lines.append("Lib\\site-packages")
    pth_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    # Step D: Ensure empty DLLs dir (some packages need it)
    dlls_dir = python_dir / "DLLs"
    dlls_dir.mkdir(exist_ok=True)

    # Step E: Install pip
    get_pip = CACHE_DIR / "get-pip.py"
    if not get_pip.is_file():
        _download_file(GET_PIP_URL, get_pip)

    _log("  Installing pip ...")
    subprocess.run(
        [str(python_dir / "python.exe"), str(get_pip)],
        check=True, capture_output=True, text=True,
    )

    # Step F: Install dependencies from repo requirements.txt
    req_file = Path(repo_path) / "requirements.txt"
    if req_file.is_file():
        _log("  Installing dependencies from requirements.txt ...")
        result = subprocess.run(
            [
                str(python_dir / "python.exe"), "-m", "pip", "install",
                "--target", str(python_dir / "Lib" / "site-packages"),
                "-r", str(req_file),
            ],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            _log("pip install failed:", err=True)
            for line in result.stderr.splitlines():
                _log(f"  {line}", err=True)
            sys.exit(1)
        # Show installed packages count
        lines = [l for l in result.stdout.splitlines() if "Installed" in l or "installed" in l]
        for l in lines:
            _log(f"  {l.strip()}")
    else:
        _log("No requirements.txt found, skipping dep install.", err=True)

    _log(f"Embedded Python ready: {python_dir}")
    return python_dir


# ---------------------------------------------------------------------------
# Step 1: Build frontend
# ---------------------------------------------------------------------------
def _build_frontend(repo_path: str) -> None:
    """Run npm run build in the repo's frontend directory."""
    frontend_dir = Path(repo_path) / "frontend"
    dist_dir = frontend_dir / "dist"

    if not (frontend_dir / "package.json").is_file():
        _log("No frontend/package.json found — skipping npm build.", err=True)
        return

    _log("Running npm install...")
    subprocess.run(
        "npm install",
        cwd=str(frontend_dir),
        check=True,
        capture_output=True,
        text=True,
        shell=True,
    )

    _log("Running npm run build (MODE=prod)...")
    env = os.environ.copy()
    env["VITE_MODE"] = "prod"
    subprocess.run(
        "npm run build",
        cwd=str(frontend_dir),
        check=True,
        capture_output=True,
        text=True,
        shell=True,
        env=env,
    )

    if not dist_dir.is_dir():
        _log("Frontend build completed but dist/ not found!", err=True)
        sys.exit(1)

    _log(f"Frontend built: {dist_dir}")


# ---------------------------------------------------------------------------
# Step 2: Compile backend to .pyc
# ---------------------------------------------------------------------------
def _compile_backend(repo_path: str) -> None:
    """Compile all .py files to legacy .pyc alongside the originals."""
    backend_dir = Path(repo_path) / "backend"
    if not backend_dir.is_dir():
        _log(f"backend/ not found at {backend_dir}", err=True)
        sys.exit(1)

    _log("Compiling backend/ to .pyc ...")
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-b", str(backend_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _log("Compilation completed with errors (may be ok).", err=True)
        for line in result.stderr.splitlines():
            _log(f"  {line}", err=True)
    else:
        _log("Compilation OK.")


# ---------------------------------------------------------------------------
# Step 3: Create clean backend copy (exclude unwanted files)
# ---------------------------------------------------------------------------
def _clean_backend_copy(repo_path: str, *, compiled: bool) -> Path:
    """Copy backend, excluding unwanted files.

    When ``compiled`` is True only ``.pyc`` files are kept (``.py`` excluded).
    Otherwise the original ``.py`` sources are kept (``.pyc`` excluded).

    Returns the path to the clean backend directory.
    """
    src = Path(repo_path) / "backend"
    dst = Path(repo_path) / BUILD_DIR_NAME / "dist" / "backend"

    if dst.exists():
        shutil.rmtree(dst)

    _log(f"Copying backend (clean) -> {dst} ...")

    for root, dirs, files in os.walk(str(src)):
        rel = Path(root).relative_to(src)

        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in BACKEND_EXCLUDED_DIRS]

        # Determine destination path
        dest_dir = dst / rel
        dest_dir.mkdir(parents=True, exist_ok=True)

        for fname in files:
            src_file = Path(root) / fname
            dest_file = dest_dir / fname

            # Compiled build: skip .py sources (only keep .pyc).
            # Source build: skip .pyc (only keep .py).
            if compiled and fname.endswith(".py") and not fname.endswith(".pyc"):
                _log(f"  Excluding: {rel / fname}")
                continue
            if not compiled and fname.endswith(".pyc"):
                _log(f"  Excluding: {rel / fname}")
                continue

            # Skip excluded files
            if fname in BACKEND_EXCLUDED_FILES:
                _log(f"  Excluding: {rel / fname}")
                continue

            # For .md and .txt: only keep if in prompts/ or allowed paths
            if fname.endswith((".md", ".txt")):
                rel_str = str(rel.as_posix())
                keep = any(rel_str.startswith(allowed) for allowed in BACKEND_KEEP_MD_TXT_PATHS)
                if not keep:
                    _log(f"  Excluding: {rel / fname}")
                    continue

            shutil.copy2(str(src_file), str(dest_file))

    _log(f"Clean backend copy: {dst}")
    return dst


# ---------------------------------------------------------------------------
# Step 4: Generate launcher and build executable
# ---------------------------------------------------------------------------
def _generate_launcher(repo_path: str, exe_name: str) -> str:
    """Generate a customized launcher.py from the template.

    Returns the path to the generated launcher file.
    """
    template_file = TEMPLATES_DIR / "launcher.py"
    if not template_file.is_file():
        _log(f"Launcher template not found: {template_file}", err=True)
        sys.exit(1)

    template_src = template_file.read_text(encoding="utf-8")

    # Replace placeholders
    launcher_src = (
        template_src
        .replace("{{APP_MODULE}}", "backend.main:app")
        .replace("{{PORT}}", "8000")
        .replace("{{EXE_NAME}}", exe_name)
    )

    build_dir = Path(repo_path) / BUILD_DIR_NAME
    build_dir.mkdir(parents=True, exist_ok=True)
    launcher_path = build_dir / "launcher.py"
    launcher_path.write_text(launcher_src, encoding="utf-8")

    _log(f"Launcher generated: {launcher_path}")
    return str(launcher_path)


def _build_executable(repo_path: str, launcher_path: str, exe_name: str) -> Path:
    """Run PyInstaller to create the executable.

    Returns the path to the generated executable.
    """
    build_dir = Path(repo_path) / BUILD_DIR_NAME

    # Determine icon path (try common locations)
    icon_candidates = [
        Path(repo_path) / "frontend" / "src" / "assets" / "logo_cliente.ico",
        Path(repo_path) / "frontend" / "public" / "logo.ico",
        Path(repo_path) / "logo.ico",
    ]
    icon_path = None
    for cand in icon_candidates:
        if cand.is_file():
            icon_path = cand
            break

    _log(f"Building executable '{exe_name}.exe' with PyInstaller ...")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--onefile",
        "--noconsole",
        "--name", exe_name,
        "--distpath", str(build_dir / "dist"),
        "--workpath", str(build_dir / "temp"),
        "--specpath", str(build_dir / "temp"),
    ]
    if icon_path:
        cmd.extend(["--icon", str(icon_path)])

    cmd.append(launcher_path)

    _log(f"  PyInstaller command: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        _log("PyInstaller build FAILED:", err=True)
        for line in result.stderr.splitlines():
            _log(f"  {line}", err=True)
        for line in result.stdout.splitlines():
            if "ERROR" in line or "Error" in line or "Traceback" in line:
                _log(f"  {line}", err=True)
        sys.exit(1)

    exe_path = build_dir / "dist" / f"{exe_name}.exe"
    if not exe_path.is_file():
        _log(f"Executable not found at {exe_path}", err=True)
        sys.exit(1)

    _log(f"Executable: {exe_path} ({exe_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return exe_path


# ---------------------------------------------------------------------------
# Step 5: Build zip
# ---------------------------------------------------------------------------
def _build_zip(repo_path: str, exe_path: Path, exe_name: str) -> Path:
    """Package everything into a zip file.

    Contents:
    - {exe_name}.exe
    - backend/         (compiled .pyc, cleaned)
    - frontend/dist/   (from repo)
    - python/          (embedded Python + deps)
    - .env             (from repo)
    - LICENSE          (from repo)
    - README.md        (from repo)
    """
    repo = Path(repo_path)
    version = _get_version(repo_path)
    repo_name = _repo_name(repo_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"{repo_name}-v{version}.zip"
    zip_path = Path(repo_path) / BUILD_DIR_NAME / zip_name

    _log(f"Creating zip: {zip_name} ...")

    with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
        entry_count = 0

        # 1. Executable
        zf.write(str(exe_path), exe_path.name)
        entry_count += 1
        _log(f"  Added: {exe_path.name}")

        # 2. backend/ (cleaned copy)
        backend_src = Path(repo_path) / BUILD_DIR_NAME / "dist" / "backend"
        if backend_src.is_dir():
            for root, dirs, files in os.walk(str(backend_src)):
                rel = Path(root).relative_to(backend_src)
                for fname in files:
                    arcname = f"backend/{rel / fname}"
                    zf.write(os.path.join(root, fname), arcname)
                    entry_count += 1
            _log(f"  Added: backend/ (cleaned, .pyc)")

        # 3. frontend/dist/
        frontend_dist = repo / "frontend" / "dist"
        if frontend_dist.is_dir():
            for root, dirs, files in os.walk(str(frontend_dist)):
                rel = Path(root).relative_to(frontend_dist)
                for fname in files:
                    arcname = f"frontend/dist/{rel / fname}"
                    zf.write(os.path.join(root, fname), arcname)
                    entry_count += 1
            _log(f"  Added: frontend/dist/")

        # 4. Embedded Python (portable, no hardcoded paths)
        python_src = Path(repo_path) / BUILD_DIR_NAME / "dist" / "python"
        if python_src.is_dir():
            for root, dirs, files in os.walk(str(python_src)):
                rel = Path(root).relative_to(python_src)
                # Skip __pycache__
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for fname in files:
                    arcname = f"python/{rel / fname}"
                    zf.write(os.path.join(root, fname), arcname)
                    entry_count += 1
            _log(f"  Added: python/ (embedded Python + deps)")

        # 5. .env
        env_file = repo / ".env"
        if env_file.is_file():
            zf.write(str(env_file), ".env")
            entry_count += 1
            _log(f"  Added: .env")

        # 6. LICENSE
        license_file = repo / "LICENSE"
        if license_file.is_file():
            zf.write(str(license_file), "LICENSE")
            entry_count += 1
            _log(f"  Added: LICENSE")

        # 7. README.md
        readme_file = repo / "README.md"
        if readme_file.is_file():
            zf.write(str(readme_file), "README.md")
            entry_count += 1
            _log(f"  Added: README.md")

        _log(f"  Total entries: {entry_count}")

    _log(f"\nZip created: {zip_path} ({zip_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return zip_path


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
def _cleanup(repo_path: str, *, keep_zip: bool = True, compiled: bool = True) -> Path | None:
    """Remove build artifacts from repo. Returns final zip path if kept."""
    build_dir = Path(repo_path) / BUILD_DIR_NAME
    final_zip: Path | None = None

    if not build_dir.is_dir():
        return None

    # Keep only the zip if requested
    if keep_zip:
        zip_files = list(build_dir.glob("*.zip"))
        # Move zip files out first, THEN delete the build directory
        for zf in zip_files:
            dest = Path(repo_path) / zf.name
            shutil.move(str(zf), str(dest))
            final_zip = dest
            _log(f"Zip moved to: {dest}")
        shutil.rmtree(str(build_dir))

    # Also clean .pyc files from original backend (only if we compiled them)
    backend_dir = Path(repo_path) / "backend"
    if compiled and backend_dir.is_dir():
        _log("Cleaning .pyc files from original backend/ ...")
        for pyc in backend_dir.rglob("*.pyc"):
            pyc.unlink(missing_ok=True)

    return final_zip


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------
def build(
    repo_path: str,
    exe_name: str,
    *,
    skip_frontend: bool = False,
    use_embed: bool = True,
    compile_backend: bool = False,
) -> Path | None:
    """Run the full build pipeline.

    Args:
        repo_path: Absolute path to the repository root.
        exe_name: Name for the generated executable.
        skip_frontend: Skip npm build and reuse existing ``frontend/dist``.
        use_embed: Download/configure embedded Python instead of using a venv.
        compile_backend: Compile ``backend/`` to ``.pyc`` (default: ship
            the ``.py`` sources as-is).

    Returns the path to the generated zip file, or None if build failed.
    """
    repo_path = str(Path(repo_path).resolve())
    total_steps = 7 if not skip_frontend else 6
    final_zip: Path | None = None
    build_dir = Path(repo_path) / BUILD_DIR_NAME

    _log(f"Starting build for: {repo_path}")
    _log(f"Executable name: {exe_name}")
    _log(f"Repo name: {_repo_name(repo_path)}")
    _log(f"Version: {_get_version(repo_path)}")
    _log(f"Python: embedded ({EMBEDDED_PYTHON_VERSION})" if use_embed else f"Python: venv (.{{repo}})")
    _log(f"Download: {EMBEDDED_PYTHON_URL}" if use_embed else "")
    _log(f"Backend: {'compiled (.pyc)' if compile_backend else 'source (.py)'}")

    # Validate
    if not Path(repo_path).is_dir():
        _log(f"Repo path not found: {repo_path}", err=True)
        sys.exit(1)

    try:
        current_step = 0

        # Step 1 — Build frontend
        if not skip_frontend:
            current_step += 1
            _step(current_step, total_steps, "Build frontend (npm run build)")
            _build_frontend(repo_path)

        # Step 2 — Compile backend (optional)
        if compile_backend:
            current_step += 1
            _step(current_step, total_steps, "Compile backend to .pyc")
            _compile_backend(repo_path)

        # Step 3 — Clean backend copy
        current_step += 1
        _step(current_step, total_steps, "Create clean backend copy")
        _clean_backend_copy(repo_path, compiled=compile_backend)

        # Step 4 — Setup embedded Python (download, pip, deps)
        if use_embed:
            current_step += 1
            _step(current_step, total_steps, "Setup embedded Python + dependencies")
            _setup_embedded_python(repo_path, build_dir)
        else:
            _log("Using existing venv (--no-embed).")

        # Step 5 — Generate launcher
        current_step += 1
        _step(current_step, total_steps, "Generate launcher and build executable")
        launcher_path = _generate_launcher(repo_path, exe_name)

        # Step 6 — Build executable
        current_step += 1
        _step(current_step, total_steps, "Build executable with PyInstaller")
        exe_path = _build_executable(repo_path, launcher_path, exe_name)

        # Step 7 — Create zip & cleanup
        current_step += 1
        _step(current_step, total_steps, "Package distribution zip")
        zip_path = _build_zip(repo_path, exe_path, exe_name)
        _log("Cleaning build artifacts ...")
        final_zip = _cleanup(repo_path, keep_zip=True, compiled=compile_backend)

        print(f"\n{'=' * 60}")
        print(f"  BUILD COMPLETE")
        print(f"  Output: {final_zip}")
        print(f"{'=' * 60}\n")

    except Exception:
        _log("Build FAILED — cleaning temporary files ...", err=True)
        _cleanup(repo_path, keep_zip=False, compiled=compile_backend)
        raise

    return final_zip


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="synapseForge - Build distribution zip for agent repos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python forge.py D:\\ia-san-juan\\4_reinas \"<cliente>nombre_cliente</cliente>\"\n"
            "  python forge.py /home/user/my-repo \"Mi App\" --skip-frontend\n"
        ),
    )
    parser.add_argument(
        "repo_path",
        help="Absolute path to the repository root",
    )
    parser.add_argument(
        "exe_name",
        help="Name for the executable (e.g. '<cliente>nombre_cliente</cliente>')",
    )
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Skip frontend build (use existing dist/)",
    )
    parser.add_argument(
        "--no-embed",
        action="store_true",
        help="Use existing venv instead of downloading embedded Python",
    )
    parser.add_argument(
        "--compile",
        "-c",
        action="store_true",
        help="Compile backend/ to .pyc (default: ship .py sources as-is)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output directory for the zip (default: repo root)",
    )

    args = parser.parse_args()
    try:
        build(
            args.repo_path,
            args.exe_name,
            skip_frontend=args.skip_frontend,
            use_embed=not args.no_embed,
            compile_backend=args.compile,
        )
    except Exception as e:
        _log(f"ERROR: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
