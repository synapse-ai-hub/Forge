<p align="center">
  <img src="../src/logo_empresa.png" alt="Logo" width="150">

---
  
</p><h1 align="center">🚀 Comandos CLI y entorno virtual</h1>

---

## ⚡ Uso

### Manual (sin configurar nada)

Ejecutar esto **cada vez** que abrís la terminal:

```powershell
.\.synapseForge\Scripts\Activate.ps1
. .\.commands\init.ps1
```

---

### Automático (una sola vez)

Para que se active solo cada vez que abrís la terminal:

#### 1. Configurar perfil de PowerShell

```powershell
code $PROFILE
```

#### 2. Pegar esto y guardar:

```powershell
# Busca .commands en la carpeta actual
if (Test-Path ".commands") {
    # Activa el entorno virtual (cualquier nombre con Scripts/Activate.ps1)
    Get-ChildItem -Directory | Where-Object {
        Test-Path "$_\Scripts\Activate.ps1"
    } | Select-Object -First 1 | ForEach-Object {
        & "$_\Scripts\Activate.ps1"
    }
    # Carga tus comandos
    . ".commands\init.ps1"
}
```

¡Listo! La próxima vez que abras la terminal se activa solo.

---

## 🧰 Comandos disponibles

| Alias | Qué hace |
|-------|----------|
| `cmds` | Lista los comandos disponibles |
| `sync` | Sincroniza con `fetch` + `rebase` (`-b` rama, default `main`) |
| `push` | Commit + push con rebase (`-m` mensaje, `-b` rama) |
| `template` | Regenera `pipeline/template.zip` desde `template/` |
| `test` | Corre los tests E2E (`--only` escenario) |

---

## 📝 Agregar Comandos

Editar .commands/commands.json:

```json
{
    "alias": "nuevo",
    "command": "python script.py",
    "description": "Descripción"
}
```

---

## 🔧 Debug

- ¿Comandos no cargan? → Reiniciar terminal
- ¿Venv no activa? → Verificar Scripts/Activate.ps1 existe