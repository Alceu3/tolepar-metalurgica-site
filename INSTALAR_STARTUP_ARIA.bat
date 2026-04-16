@echo off
echo Instalando ARIA no startup do Windows...
PowerShell -ExecutionPolicy Bypass -File "%~dp0agente\instalar_startup.ps1"
pause
