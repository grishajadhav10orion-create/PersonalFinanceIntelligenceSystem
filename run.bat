@echo off
rem One-click start for Windows
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe ( echo Setting up first run... & python -m venv .venv )
if not exist .venv\Scripts\python.exe ( echo Could not create the virtual environment. Install Python 3 from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^) and run this again. & pause & exit /b 1 )
call .venv\Scripts\activate.bat
rem pip cannot upgrade itself via pip.exe on Windows, so go through python -m pip (and do not stop if the upgrade fails)
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt
if errorlevel 1 ( echo Installing requirements failed. Check your internet connection and run this again. & pause & exit /b 1 )
python scripts\load_demo.py
echo.
echo Open http://localhost:5001  (login: demo / demo1234).  Press Ctrl+C to stop.
python app.py
pause
