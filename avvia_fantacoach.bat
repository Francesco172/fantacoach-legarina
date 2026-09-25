@echo off
cd /d "%~dp0"
start "" http://127.0.0.1:8787
py server.py 2>nul || python server.py
pause
