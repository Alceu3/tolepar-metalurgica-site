$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = "../.venv/Scripts/python.exe"
if (-not (Test-Path $python)) {
  Write-Host "Python virtualenv nao encontrado. Rode primeiro .\instalar_agente.ps1" -ForegroundColor Red
  exit 1
}

Write-Host "Iniciando ARIA..." -ForegroundColor Green
& $python main.py
