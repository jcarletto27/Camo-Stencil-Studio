@echo off
TITLE Camo Studio

:: 0. AUTO-UPDATE CHECK
ECHO [*] Checking for updates...
git --version >nul 2>&1
IF %ERRORLEVEL% EQU 0 (
    git pull origin main
) ELSE (
    ECHO [!] Git not found. Skipping update check.
)
ECHO.

:: 1. RUN APP
IF NOT EXIST "venv" (
    ECHO [!] Virtual environment not found! Please run setup_windows.bat first.
    PAUSE
    EXIT /B
)

CALL venv\Scripts\activate.bat
python camo_studio.py
PAUSE
