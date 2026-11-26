@echo off
title Empire Tweaks - website preview
cd /d "%~dp0"
echo Installing what the site needs (first time only)...
python -m pip install -q flask flask-cors requests firebase-admin
echo.
echo Opening http://localhost:10000  (close this window to stop the site)
start "" http://localhost:10000
python server.py
pause
