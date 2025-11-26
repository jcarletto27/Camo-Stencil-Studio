@echo off
TITLE Camo Studio - Automated Setup
CLS

ECHO ========================================================
ECHO      CAMO STUDIO - ENVIRONMENT SETUP WIZARD
ECHO ========================================================
ECHO.

:: 0. CHECK FOR UPDATES (GIT)
ECHO [*] Checking for Git installation...
git --version >nul 2>&1
IF %ERRORLEVEL% EQU 0 (
    ECHO [OK] Git found. Attempting to pull latest updates...
    git pull origin main
    IF %ERRORLEVEL% NEQ 0 (
        ECHO [!] Git pull failed or not a git repository. Continuing with local version.
    ) ELSE (
        ECHO [OK] Successfully updated to latest version.
    )
) ELSE (
    ECHO [!] Git not found. Skipping auto-update.
)
ECHO.

:: 1. CHECK FOR PYTHON
ECHO [*] Checking for Python installation...
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    ECHO [!] Python is not detected! 
    ECHO     Please install Python 3.10 or newer from python.org
    ECHO     Make sure to check "Add Python to PATH" during installation.
    PAUSE
    EXIT /B
)
ECHO [OK] Python found.
ECHO.

:: 2. CREATE VIRTUAL ENVIRONMENT
IF EXIST "venv" (
    ECHO [*] Virtual environment 'venv' already exists. Skipping creation.
) ELSE (
    :: Fixed: Removed parentheses from the text below to prevent syntax errors
    ECHO [*] Creating virtual environment - this may take a moment...
    python -m venv venv
    
    :: Check for error immediately after command
    IF ERRORLEVEL 1 (
        ECHO [!] Failed to create virtual environment.
        PAUSE
        EXIT /B
    )
    ECHO [OK] Virtual environment created.
)
ECHO.

:: 3. ACTIVATE AND INSTALL
ECHO [*] Activating virtual environment...
CALL venv\Scripts\activate.bat

ECHO [*] Upgrading pip...
python -m pip install --upgrade pip

ECHO.
ECHO [*] Installing required libraries...
ECHO     (opencv-python, numpy, svgwrite, Pillow, trimesh, shapely, scipy, mapbox_earcut)
ECHO.

:: Install directly to ensure all specific libs are present even if requirements.txt is missing
:: Using ^ to split the command across multiple lines for readability
pip install opencv-python ^
numpy ^
svgwrite ^
Pillow ^
trimesh ^
shapely ^
scipy ^
mapbox_earcut

IF %ERRORLEVEL% NEQ 0 (
    ECHO.
    ECHO [!] There was an error installing dependencies.
    PAUSE
    EXIT /B
)

ECHO.
ECHO ========================================================
ECHO [OK] SETUP COMPLETE!
ECHO ========================================================
ECHO.
ECHO You can now run the application using 'run.bat'
ECHO.
PAUSE
