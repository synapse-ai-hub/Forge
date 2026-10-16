# init.ps1 - synapseForge CLI Loader
# Uso: . .\init.ps1

# Configuración de salida
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$jsonPath = Join-Path $PSScriptRoot "commands.json"

Write-Host ""
Write-Host "  synapseForge | Global Framework" -ForegroundColor Cyan
Write-Host "  ------------------------------------------------" -ForegroundColor DarkGray

if (Test-Path $jsonPath) {
    try {
        $config = Get-Content $jsonPath -Raw | ConvertFrom-Json
        $loaded = @()
        
        foreach ($cmd in $config.commands) {
            $name = $cmd.alias
            $exec = $cmd.command
            
            # Crear función global
            $scriptBlock = [scriptblock]::Create("$exec `$args")
            Set-Item -Path "Function:Global:$name" -Value $scriptBlock
            $loaded += $name
        }
        
        Write-Host "  > Aliases: " -NoNewline -ForegroundColor White
        Write-Host "$(($loaded) -join ', ')" -ForegroundColor Green
        Write-Host "  > Root:    " -NoNewline -ForegroundColor White
        Write-Host "$PSScriptRoot" -ForegroundColor DarkGray
    } catch {
        Write-Warning "Error al procesar commands.json: $($_.Exception.Message)"
    }
} else {
    Write-Warning "Configuración no encontrada en: $jsonPath"
}

Write-Host "  ------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""
