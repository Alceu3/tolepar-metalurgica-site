@echo off
cd /d "%~dp0agente_nuvem"
if exist "..\.venv\Scripts\python.exe" (
  "..\.venv\Scripts\python.exe" -m pip install -r requirements.txt
) else (
  python -m pip install -r requirements.txt
)
pause
