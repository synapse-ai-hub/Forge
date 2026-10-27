"""Run the E2E tests quickly.

Usage:
    python .commands/commands/quick_test.py              # All the scenarios
    python .commands/commands/quick_test.py rag          # Only scenarios with "rag" in the name
    python .commands/commands/quick_test.py scheduler    # Only scenarios with "scheduler"

Parameters:
    scenario: Substring to filter the scenarios (optional, default: all).
    --url: Backend base URL (optional, default: http://127.0.0.1:8000).
"""
import sys
import subprocess
import argparse


def main() -> None:
    """Funcion principal"""
    parser = argparse.ArgumentParser(
        description="Correr tests E2E del proyecto",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python .commands/commands/quick_test.py
  python .commands/commands/quick_test.py rag
  python .commands/commands/quick_test.py scheduler --url http://127.0.0.1:8000
        """,
    )

    parser.add_argument(
        "scenario",
        nargs="?",
        default=None,
        help="Substring para filtrar escenarios (ej: rag, scheduler, creators)",
    )

    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000",
        help="Backend base URL (default: http://127.0.0.1:8000)",
    )

    args = parser.parse_args()

    cmd = [sys.executable, "-m", "tests.e2e.runner", "--base-url", args.url]

    if args.scenario:
        cmd.extend(["--only", args.scenario])

    print(f"\n🧪 Ejecutando tests E2E...\n")
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
