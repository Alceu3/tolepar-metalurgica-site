@echo off
taskkill /F /IM pythonw.exe /T >nul 2>&1
taskkill /F /IM python.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul
start "" "c:\Users\ACER\projeto html\.venv\Scripts\pythonw.exe" "c:\Users\ACER\projeto html\agente\widget.py"
