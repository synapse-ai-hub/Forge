"""
Script para sincronizar repositorio con fetch + rebase.

Uso:
    python .commands/commands/quick_sync.py           # Sync con main
    python .commands/commands/quick_sync.py -b develop # Sync con develop
    
Parámetros:
    -b : Rama con la que sincronizar (opcional, default: main)
"""
import sys
import subprocess
import argparse


def run_command(command: str, description: str) -> bool:
    """
    Ejecuta un comando git y maneja errores.
    
    Args:
        command: Comando a ejecutar
        description: Descripción para mostrar
        
    Returns:
        True si exitoso, False si falla
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


def main():
    """Función principal"""
    parser = argparse.ArgumentParser(
        description='Sincronizar con fetch + rebase',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python .commands/commands/quick_sync.py              # Sync con main
  python .commands/commands/quick_sync.py -b develop   # Sync con develop
        """
    )
    
    parser.add_argument(
        '-b',
        '--branch',
        default='main',
        help='Rama con la que sincronizar (default: main)'
    )
    
    args = parser.parse_args()
    
    print(f"\n🔄 Sincronizando con origin/{args.branch}...\n")
    
    # 1. Git fetch
    if not run_command(f'git fetch origin', 'Descargando cambios remotos'):
        return False
    
    # 2. Git rebase
    if not run_command(f'git rebase origin/{args.branch}', f'Aplicando rebase con origin/{args.branch}'):
        print("\n❌ Rebase falló. Resuelve conflictos manualmente.")
        print("   Luego ejecuta: git rebase --continue")
        print("   O aborta con: git rebase --abort")
        return False
    
    print(f"\n✅ Sincronización completada con origin/{args.branch}\n")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
