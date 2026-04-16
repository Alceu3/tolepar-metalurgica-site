@echo off
cd /d "%~dp0agente_nuvem"
if exist "..\.venv\Scripts\python.exe" (
  "..\.venv\Scripts\python.exe" local_bridge.py pull
) else (
  python local_bridge.py pull
)
pause
