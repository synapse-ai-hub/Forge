"""CLI entry point — ``synapseForge init``, ``synapseForge launch``, ``synapseForge colors``, ``synapseForge run``.

Installed via ``pyproject.toml`` entry point::

    synapseForge init [target_dir]
    synapseForge launch [-p PATH] -n NAME [--skip-frontend] [--no-embed] [-c]
    synapseForge colors [project_dir]
    synapseForge run [project_dir]

Examples:
    synapseForge init                    # Create project in current directory
    synapseForge init ./mi-proyecto      # Create project in ./mi-proyecto
    synapseForge launch -n mi-app        # Build distribution zip (current dir)
    synapseForge launch -p ./mi-proyecto -n mi-app  # Build from specific project
    synapseForge launch -n mi-app --skip-frontend   # Skip frontend build
    synapseForge launch -n mi-app -c                # Compile backend to .pyc
    synapseForge colors                  # Edit colors in current project
    synapseForge colors ./mi-proyecto    # Edit colors in specific project
    synapseForge update ./mi-proyecto    # Update project to latest template
    synapseForge run                     # Start dev servers (uvicorn + npm)
    synapseForge run ./mi-proyecto       # Start dev servers in specific project
"""

from __future__ import annotations

import argparse
import json
import re
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

COLOR_FIELDS = [
    ("primary", "Color principal (botones, headers, burbujas)"),
    ("secondary", "Color secundario (hover, detalles light)"),
    ("primary_text", "Color de texto (botones, headers)"),
    ("gradient_secondary", "Color secundario del gradiente"),
]


def main() -> None:
    """Parse arguments and dispatch to ``pipeline.init`` or ``pipeline.launch``."""
    parser = argparse.ArgumentParser(
        prog="synapseForge",
        description="synapseForge — AI agent project scaffolding & distribution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    # ── init ────────────────────────────────────────────────────────────
    init_p = subparsers.add_parser(
        "init",
        help="Create a new synapseForge project from template",
        description="Create a new synapseForge project from template. Opens a GUI to collect project configuration (name, description, colors, etc.) and generates the complete project structure.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapseForge init                    # Create project in current directory
  synapseForge init ./mi-proyecto      # Create project in ./mi-proyecto
  synapseForge init /ruta/absoluta     # Create project in absolute path

The GUI will prompt for:
  - Project name, description, client/task names
  - Logo files (company + client)
  - Primary, secondary, text color and gradient colors for the UI

Output: Complete project structure with backend/, frontend/, config/, src/ and the Docker files""",
    )
    init_p.add_argument(
        "target_dir",
        nargs="?",
        default=".",
        help="Target directory (default: current working directory)",
    )

    # ── launch ──────────────────────────────────────────────────────────
    launch_p = subparsers.add_parser(
        "launch",
        help="Build a standalone distribution zip from a project",
        description="Build a standalone distribution zip from a synapseForge project. Packages the backend (with embedded Python), frontend (built), and creates a Windows executable launcher.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapseForge launch -n mi-app                    # Build distribution (current dir)
  synapseForge launch -p ./mi-proyecto -n mi-app   # Build from specific project
  synapseForge launch -n mi-app --skip-frontend    # Use existing frontend/dist
  synapseForge launch -n mi-app --no-embed         # Use system Python (no embed)

Arguments:
  -p, --path   Path to the project root (default: current directory)
  -n, --name   Name for the executable (e.g., mi-app -> mi-app.exe) [required]

Options:
  --skip-frontend   Skip npm build, use existing frontend/dist/
  --no-embed        Use existing venv instead of downloading embedded Python
  -c, --compile     Compile backend/ to .pyc (default: ship .py sources)

Output: <project>/<project>-v<version>.zip, a portable app that runs with a double click""",
    )
    launch_p.add_argument(
        "-p",
        "--path",
        default=".",
        help="Path to the project root (default: current working directory)",
    )
    launch_p.add_argument(
        "-n",
        "--name",
        required=True,
        help="Name for the executable (e.g., mi-app)",
    )
    launch_p.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Skip npm build (use existing frontend/dist/)",
    )
    launch_p.add_argument(
        "--no-embed",
        action="store_true",
        help="Use existing venv instead of downloading embedded Python",
    )
    launch_p.add_argument(
        "-c",
        "--compile",
        action="store_true",
        help="Compile backend/ to .pyc (default: ship .py sources as-is)",
    )

    # ── colors ──────────────────────────────────────────────────────────
    colors_p = subparsers.add_parser(
        "colors",
        help="Edit runtime colors.json (frontend/public/colors.json) via GUI",
        description="Open a tkinter GUI to edit the runtime colors.json file. Changes apply immediately on browser reload — no rebuild needed.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapseForge colors                  # Edit colors in current project
  synapseForge colors ./mi-proyecto    # Edit colors in specific project

The GUI allows editing:
  - Primary color (buttons, headers, bubbles)
  - Secondary color (hover, details light)
  - Text color for buttons and headers
  - Gradient secondary color (with toggle to enable/disable gradients)

Changes are saved to frontend/public/colors.json and take effect on browser refresh.""",
    )
    colors_p.add_argument(
        "project_dir",
        nargs="?",
        default=".",
        help="Project directory containing frontend/public/colors.json (default: current)",
    )

    # ── run ─────────────────────────────────────────────────────────────
    run_p = subparsers.add_parser(
        "run",
        help="Start development servers (uvicorn + npm run dev) and open browser",
        description="Start both backend (uvicorn with --reload) and frontend (npm run dev) development servers. The project's venv must be active. The frontend opens the default browser.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapseForge run                     # Start dev servers in current project
  synapseForge run ./mi-proyecto       # Start dev servers in specific project

What it does:
  1. Checks that the project's venv is active (VIRTUAL_ENV)
  2. Starts uvicorn on port 8000 (backend.main:app with --reload) and waits for /health
  3. Starts npm run dev (Vite) on port 3000 (frontend/), which opens the browser

Press Ctrl+C to stop both servers.

Requirements:
  - Project created with synapseForge init
  - Node.js + npm installed
  - Frontend dependencies installed (npm install in frontend/)""",
    )
    run_p.add_argument(
        "project_dir",
        nargs="?",
        default=".",
        help="Project root directory (default: current working directory)",
    )

    # ── update ──────────────────────────────────────────────────────────
    update_p = subparsers.add_parser(
        "update",
        help="Update project to latest template",
        description="Update the project to the latest template version from GitHub. Before overwriting, the entire project is backed up to ~/.config/synapseForge/backup/. If the update fails, the project is automatically restored.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapseForge update                    # Update project in current directory
  synapseForge update ./mi-proyecto      # Update specific project

What happens:
  1. Backs up the entire project to ~/.config/synapseForge/backup/
  2. Downloads the latest template from GitHub
  3. Extracts and overwrites base files (backend, frontend structure)
  4. Re-applies your saved configuration (placeholders, colors)
  5. On failure: restores from backup automatically
  6. On success: asks whether to keep or delete the backup

Preserved across updates:
  - Your config (replace.json, colors, logos)
  - Your agent.db and provider keys
  - Your skills, tools, agents, knowledge collections

Not preserved (overwritten):
  - Backend Python files (model_resolver.py, etc.)
  - Frontend source files
  - Pipeline scripts""",
    )
    update_p.add_argument(
        "project_dir",
        nargs="?",
        default=".",
        help="Project root directory (default: current working directory)",
    )

    args = parser.parse_args()

    try:
        if args.command == "init":
            _init(args.target_dir)
        elif args.command == "update":
            _update(args.project_dir)
        elif args.command == "launch":
            _launch(args.path, args.name, args.skip_frontend, args.no_embed, args.compile)
        elif args.command == "colors":
           _colors(args.project_dir)
        elif args.command == "run":
            _run(args.project_dir)
        else:
            parser.print_help()
            sys.exit(1)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


def _init(target_dir: str) -> None:
    """Open tkinter GUI to collect config, then run pipeline.init.main.run()."""
    try:
        from synapseforge.tk.init_app import InitApp
    except ImportError as exc:
        print(f"ERROR: could not load GUI module — {exc}", file=sys.stderr)
        sys.exit(1)

    config = InitApp.launch(target_dir)
    if config is None:
        print("  Inicialización cancelada.")
        return

    print("  Proyecto creado correctamente.")


def _update(project_dir: str) -> None:
    """Import and run pipeline.update.main.run_update()."""
    try:
        from pipeline.update.main import run_update
    except ImportError as exc:
        print(f"ERROR: could not load update module — {exc}", file=sys.stderr)
        sys.exit(1)
    run_update(project_dir)


def _launch(
    repo_path: str,
    exe_name: str,
    skip_frontend: bool,
    no_embed: bool,
    compile_backend: bool = False,
) -> None:
    """Import and run pipeline.launch.forge.build()."""
    try:
        from pipeline.launch.forge import build
    except ImportError as exc:
        print(f"ERROR: could not load launch module — {exc}", file=sys.stderr)
        sys.exit(1)
    build(
        repo_path,
        exe_name,
        skip_frontend=skip_frontend,
        use_embed=not no_embed,
        compile_backend=compile_backend,
    )


def _colors(project_dir: str) -> None:
    """Open tkinter GUI for editing frontend/public/colors.json."""
    try:
        from synapseforge.tk.colors_app import ColorsApp
    except ImportError as exc:
        print(f"ERROR: could not load GUI module — {exc}", file=sys.stderr)
        sys.exit(1)

    result = ColorsApp.launch(project_dir)
    if result is not None:
        project_path = Path(project_dir).resolve()
        colors_path = project_path / "frontend" / "public" / "colors.json"
        print(f"\n✓ Colores actualizados en {colors_path}")
        print("  Recargá el navegador para ver los cambios (sin rebuild).")


def _wait_for_backend(proc: subprocess.Popen, host: str, port: int, timeout: float = 60.0) -> None:
    """Block until the backend /health endpoint responds or the process dies.

    Args:
        proc: The uvicorn subprocess (checked for early exit).
        host: Backend host.
        port: Backend port.
        timeout: Maximum seconds to wait.

    Raises:
        SystemExit: If the backend process exits early or the timeout is reached.
    """
    url = f"http://{host}:{port}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            print("  ERROR: Backend falló al iniciar (¿olvidaste activar el venv?)", file=sys.stderr)
            sys.exit(1)
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception:
            pass  # Backend still starting — keep waiting
        time.sleep(1)
    print(f"  ERROR: El backend no respondió en {url} tras {int(timeout)}s", file=sys.stderr)
    proc.terminate()
    proc.wait()
    sys.exit(1)


def _run(project_dir: str) -> None:
    """Start uvicorn + npm run dev and open the browser."""
    import os

    # ── Verificar que el entorno virtual esté activado ────────────────
    if not os.environ.get("VIRTUAL_ENV"):
        raise RuntimeError(
            "No hay un entorno virtual activado. "
            "Activá el venv antes de ejecutar 'synapseForge run'.\n"
            "Ejemplo: .\\venv\\Scripts\\activate (Windows) o source venv/bin/activate (Linux/Mac)"
        )

    project_path = Path(project_dir).resolve()
    frontend_path = project_path / "frontend"
    backend_module = "backend.main:app"

    if not frontend_path.is_dir():
        print(f"ERROR: No se encontró el directorio frontend en {project_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Starting dev servers for {project_path} ...")

    # Start uvicorn (backend) — venv debe estar activo manualmente
    print("  Iniciando backend (uvicorn)...")
    uvicorn_proc = subprocess.Popen(
        ["python", "-m", "uvicorn", backend_module, "--reload", "--port", "8000"],
        cwd=str(project_path),
        shell=True,
    )

    # Wait for the backend to be fully up before starting the frontend
    print("  Esperando a que el backend esté listo...")
    _wait_for_backend(uvicorn_proc, host="127.0.0.1", port=8000, timeout=60)

    print("  Backend iniciado correctamente")

    # Start npm run dev (frontend)
    print("  Iniciando frontend (npm run dev)...")
    npm_proc = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=str(frontend_path),
        shell=True,
    )

    time.sleep(3)
    if npm_proc.poll() is not None:
        print("  ERROR: Frontend falló al iniciar", file=sys.stderr)
        uvicorn_proc.terminate()
        uvicorn_proc.wait()
        sys.exit(1)

    print("  Frontend iniciado correctamente")

    print("\nPresioná Ctrl+C para detener ambos servidores.\n")

    def _stop(signum=None, frame=None) -> None:
        """Force-kill both process trees and exit.

        ``shell=True`` wraps each command in ``cmd.exe``, so ``terminate()``
        alone would leave the real uvicorn/node children alive. We use
        ``taskkill /F /T`` to kill the whole tree. This also force-kills
        uvicorn even when it is stuck in a graceful shutdown waiting for open
        SSE connections.

        Before force-killing, we give the backend a chance to run its graceful
        shutdown (which frees the local Ollama model) by hitting ``/api/shutdown``.
        """
        print("\nDeteniendo servidores...")
        # Darle chance al backend de liberar el modelo antes de matarlo
        try:
            import urllib.request

            urllib.request.urlopen("http://127.0.0.1:8000/api/shutdown", timeout=2)
            time.sleep(5)
        except Exception:
            pass
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(uvicorn_proc.pid)], capture_output=True)
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(npm_proc.pid)], capture_output=True)
        print("Servidores detenidos.")
        sys.exit(0)

    # Handle Ctrl+C via a signal handler instead of a blocking wait(). A plain
    # ``uvicorn_proc.wait()`` can hang forever because uvicorn's graceful
    # shutdown waits for open SSE connections ("Waiting for connections to
    # close"). Polling with a short sleep keeps the main thread interruptible so
    # the handler runs immediately on Ctrl+C.
    signal.signal(signal.SIGINT, _stop)
    try:
        while True:
            if uvicorn_proc.poll() is not None or npm_proc.poll() is not None:
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        _stop()


if __name__ == "__main__":
    main()