@echo off
if "%~1"=="" goto usage
if "%~2"=="" goto usage
cd /d "%~dp0agente_nuvem"
if exist "..\.venv\Scripts\python.exe" (
  "..\.venv\Scripts\python.exe" local_bridge.py push "%~1" "%~2"
) else (
  python local_bridge.py push "%~1" "%~2"
)
pause
goto :eof

:usage
echo Uso:
echo ENVIAR_RESULTADO_NUVEM.bat PED-YYYYMMDD-HHMMSS-001 "C:\caminho\da\pasta"
pause
