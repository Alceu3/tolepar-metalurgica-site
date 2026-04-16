@echo off
cd /d "%~dp0agente"
powershell -ExecutionPolicy Bypass -Command "& { ..\\.venv\\Scripts\\python.exe main.py }"
pause
