# Cria atalho "Evelyn" na Area de Trabalho e no Startup (inicializar com Windows)
$agentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$vbs = Join-Path $agentDir "iniciar_evelyn.vbs"

$wsh = New-Object -ComObject WScript.Shell

# --- Atalho na Area de Trabalho ---
$desktop = [Environment]::GetFolderPath("Desktop")
$link = $wsh.CreateShortcut("$desktop\Evelyn.lnk")
$link.TargetPath   = "wscript.exe"
$link.Arguments    = "`"$vbs`""
$link.WorkingDirectory = $agentDir
$link.Description  = "Iniciar agente Evelyn"
$link.WindowStyle  = 1
$link.Save()
Write-Host "Atalho criado na Area de Trabalho: $desktop\Evelyn.lnk" -ForegroundColor Green

# --- Atalho no Startup (inicia com o Windows) ---
$startup = [Environment]::GetFolderPath("Startup")
$link2 = $wsh.CreateShortcut("$startup\Evelyn.lnk")
$link2.TargetPath       = "wscript.exe"
$link2.Arguments        = "`"$vbs`""
$link2.WorkingDirectory = $agentDir
$link2.Description      = "Evelyn - Agente IA (autostart)"
$link2.WindowStyle      = 1
$link2.Save()
Write-Host "Atalho de inicializacao criado: $startup\Evelyn.lnk" -ForegroundColor Green

Write-Host ""
Write-Host "Pronto! Evelyn vai iniciar automaticamente com o Windows." -ForegroundColor Cyan
Write-Host "Clique duas vezes em Evelyn na area de trabalho para abrir agora." -ForegroundColor Cyan
