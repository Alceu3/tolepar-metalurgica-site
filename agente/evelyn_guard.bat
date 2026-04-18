@echo off
:loop
"c:\Users\ACER\projeto html\.venv\Scripts\pythonw.exe" "c:\Users\ACER\projeto html\agente\widget.py"
timeout /t 2 /nobreak >nul
goto loop
