# ============================================================
#  Instalar ARIA no startup do Windows (pasta Startup do usuário)
#  Nao precisa de administrador
# ============================================================

$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonExe  = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"
$WidgetPy   = Join-Path $ProjectDir "agente\widget.py"
$StartupDir = [System.Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupDir "ARIA.lnk"

Write-Host "Instalando ARIA no startup do Windows..."
Write-Host "  Python  : $PythonExe"
Write-Host "  Script  : $WidgetPy"
Write-Host "  Startup : $StartupDir"

# Cria atalho .lnk na pasta Startup
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath       = $PythonExe
$Shortcut.Arguments        = "`"$WidgetPy`""
$Shortcut.WorkingDirectory = (Split-Path $WidgetPy)
$Shortcut.WindowStyle      = 7  # minimizado / sem janela
$Shortcut.Description      = "ARIA Widget"
$Shortcut.Save()

Write-Host ""
Write-Host "ARIA vai iniciar automaticamente toda vez que voce ligar o PC!" -ForegroundColor Green
Write-Host "Atalho criado em: $ShortcutPath"
Write-Host ""
Write-Host "Para remover: execute remover_startup.ps1"
