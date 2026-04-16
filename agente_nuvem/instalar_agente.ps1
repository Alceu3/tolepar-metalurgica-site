$ErrorActionPreference = "Stop"

Write-Host "== ARIA Installer ==" -ForegroundColor Cyan
Set-Location $PSScriptRoot

$python = "../.venv/Scripts/python.exe"
if (-not (Test-Path $python)) {
  Write-Host "Ambiente virtual nao encontrado. Criando .venv na raiz do projeto..." -ForegroundColor Yellow
  Set-Location ".."
  py -m venv .venv
  Set-Location "agente"
  $python = "../.venv/Scripts/python.exe"
}

Write-Host "Instalando dependencias Python..." -ForegroundColor Green
& $python -m pip install --upgrade pip
& $python -m pip install -r requirements.txt

$ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
if ($null -eq $ollamaCmd) {
  Write-Host "Ollama nao encontrado no sistema." -ForegroundColor Yellow
  Write-Host "Baixe e instale em: https://ollama.com/download" -ForegroundColor Yellow
  Write-Host "Depois rode novamente este script para baixar os modelos." -ForegroundColor Yellow
  exit 0
}

Write-Host "Verificando servico Ollama..." -ForegroundColor Green
try {
  ollama list | Out-Null
} catch {
  Write-Host "Nao foi possivel acessar o Ollama. Abra o app Ollama e rode de novo." -ForegroundColor Yellow
  exit 0
}

Write-Host "Baixando modelos locais (pode demorar)..." -ForegroundColor Green
ollama pull llama3.2:3b
ollama pull moondream:latest

Write-Host "Instalacao concluida." -ForegroundColor Cyan
Write-Host "Para iniciar: .\iniciar_agente.ps1" -ForegroundColor Cyan
