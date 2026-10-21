"""List the commands of .commands/commands.json."""

import json
from pathlib import Path

def list_commands() -> None:
    """Show the available commands with format and colors."""
    json_path = Path('.commands/commands.json')
    
    if not json_path.exists():
        print("❌ No se encontró commands.json")
        return
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        commands = data.get('commands', [])
        
        # Colores ANSI
        RESET = "\033[0m"
        CYAN = "\033[96m"
        GREEN = "\033[92m"
        YELLOW = "\033[93m"
        BLUE = "\033[94m"
        MAGENTA = "\033[95m"
        DARK_GRAY = "\033[90m"
        
        # Encabezado
        print(f"\n{YELLOW}╔════════════════════════════════════════╗")
        print(f"║               synapseForge               ║")
        print(f"╚════════════════════════════════════════╝{RESET}")
        
        print(f"{DARK_GRAY}  Comandos disponibles:{RESET}")
        print(f"{DARK_GRAY}  ──────────────────────{RESET}")
        
        # Mostrar comandos (excluyendo 'cmds')
        for cmd in commands:
            if cmd.get('alias') == 'cmds':
                continue
                
            alias = cmd.get('alias', '')
            desc = cmd.get('description', '')
            
            # Formato bonito
            print(f"  {GREEN}▶{RESET} {YELLOW}{alias:<10}{RESET} {BLUE}→{RESET} {desc}")
        
        # Pie
        print(f"\n{DARK_GRAY}  Usa: {GREEN}<comando>{RESET} {DARK_GRAY}para ejecutar{RESET}")
        print(f"{DARK_GRAY}  Ej:  {GREEN}push -m [comentario]{RESET} {DARK_GRAY}ejecuta{RESET} {MAGENTA}git add .{RESET}{DARK_GRAY},{RESET} {MAGENTA}git commit -m comentario{RESET} {DARK_GRAY}y{RESET} {MAGENTA}git push origin main{RESET}\n")
        
    except json.JSONDecodeError as e:
        print(f"❌ Error en JSON: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    list_commands()