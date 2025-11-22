@echo off
TITLE Camo Studio
IF NOT EXIST "venv" (
	    ECHO [!] Virtual environment not found! Please run setup_windows.bat first.
	        PAUSE
	            EXIT /B
	            )

	            CALL venv\Scripts\activate.bat
	            python camo_studio.py
	            PAUSE
)
