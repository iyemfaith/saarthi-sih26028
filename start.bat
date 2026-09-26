@echo off
rem SAARTHI prototype - start the local server and open the dashboard.
cd /d "%~dp0"
echo Starting SAARTHI on http://127.0.0.1:8026  (Ctrl+C to stop)
start "" http://127.0.0.1:8026
py -m uvicorn saarthi.api:app --host 127.0.0.1 --port 8026
