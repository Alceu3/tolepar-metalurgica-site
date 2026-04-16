@echo off
cd /d "%~dp0agente_nuvem"
if exist "..\.venv\Scripts\python.exe" (
  "..\.venv\Scripts\python.exe" server.py
) else (
  python server.py
)
pause
