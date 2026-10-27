"""Quick push with automatic rebase.

Usage:
    python .commands/commands/quick_push.py -m "commit message" -b main
    python .commands/commands/quick_push.py -m "fix bug" -b develop

Parameters:
    -m: Commit message (required).
    -b: Branch to push to (optional, default: main).
"""
import sys
import subprocess
import argparse


def run_command(command: str, description: str) -> bool:
    """Run a git command and handle errors.

    Args:
        command: Command to run.
        description: Description to show.

    Returns:
        True if it succeeded, False if it fails.
    """
    print(f"→ {description}...")
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        
        if result.stdout:
            print(result.stdout.strip())
            
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR: {e.stderr.strip() if e.stderr else str(e)}")
        return False


def main() -> bool:
    """Parse the arguments, commit, rebase and push.

    Returns:
        True if the push succeeded, False otherwise.
    """
    parser = argparse.ArgumentParser(
        description='Push rápido con rebase automático',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python .commands/commands/quick_push.py -m "fix: corregir bug en scoring"
  python .commands/commands/quick_push.py -m "feat: agregar query_context" -b develop
        """
    )
    
    parser.add_argument(
        '-m',
        '--message',
        required=True,
        help='Mensaje del commit'
    )
    
    parser.add_argument(
        '-b',
        '--branch',
        default='main',
        help='Rama objetivo (default: main)'
    )
    
    args = parser.parse_args()
    
    print("\n🚀 Iniciando push rápido...\n")
    
    # 1. Git add
    if not run_command('git add .', 'Agregando cambios'):
        return False
    
    # 2. Git commit
    commit_cmd = f'git commit -m "{args.message}"'
    if not run_command(commit_cmd, 'Creando commit'):
        print("⚠️  No hay cambios para commitear o falló el commit")
        # Continuar de todas formas por si solo queremos hacer push
    
    # 3. Git fetch
    if not run_command(f'git fetch origin', 'Descargando cambios remotos'):
        return False
    
    # 4. Git rebase
    if not run_command(f'git rebase origin/{args.branch}', f'Aplicando rebase con origin/{args.branch}'):
        print("\n❌ Rebase falló. Resuelve conflictos manualmente.")
        print("   Luego ejecuta: git rebase --continue")
        print("   O aborta con: git rebase --abort")
        return False
    
    # 5. Git push
    if not run_command(f'git push origin HEAD:{args.branch}', f'Pusheando a origin/{args.branch}'):
        print("\n❌ Push falló. Puede que necesites hacer pull primero.")
        return False
    
    print(f"\n✅ Push completado exitosamente a origin/{args.branch}\n")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
