@echo off
cd /d "%~dp0"
echo Open http://127.0.0.1:8000 in your browser once the server is ready.
echo Keep this window open while using MINDWEAVE.
".venv\Scripts\python.exe" -m mindweave.web
pause
