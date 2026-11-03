@echo off
title School Management System
cd /d "%~dp0"

echo ============================================================
echo   ST. JOSEPHS CONVENT SCHOOL - MANAGEMENT SYSTEM
echo ============================================================
echo.

REM --- Is Python installed and on PATH? ---
python --version >nul 2>&1
if errorlevel 1 (
    echo   PROBLEM: Python is not installed, or was installed without
    echo            ticking "Add Python to PATH".
    echo.
    echo   Fix: download Python from https://python.org/downloads
    echo        During installation, TICK "Add Python to PATH".
    echo        Then run this file again.
    echo.
    pause
    exit /b 1
)

REM --- Are the required packages present? Install once if not. ---
python -c "import fastapi, uvicorn, sqlalchemy, jinja2, openpyxl, bcrypt, itsdangerous, multipart" >nul 2>&1
if errorlevel 1 (
    echo   First-time setup: installing required components.
    echo   This takes 2-3 minutes and happens only once.
    echo.
    python -m pip install --upgrade pip >nul 2>&1
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo   PROBLEM: installation failed. Check the internet connection.
        echo.
        pause
        exit /b 1
    )
    echo.
    echo   Setup complete.
    echo.
)

REM --- Start the system ---
python run.py

echo.
echo   The system has stopped.
pause
