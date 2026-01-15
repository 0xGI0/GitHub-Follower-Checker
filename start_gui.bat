@echo off
echo.
echo ========================================
echo   GitHub Follower Checker GUI
echo ========================================
echo.

REM Pruefe ob Python installiert ist
python --version >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Python ist nicht installiert oder nicht im PATH!
    echo Bitte installiere Python von https://www.python.org/
    echo.
    pause
    exit /b 1
)

echo Pruefe Dependencies...
python -c "import customtkinter" >nul 2>&1
if errorlevel 1 (
    echo.
    echo FEHLER: customtkinter ist nicht installiert!
    echo.
    echo Installiere Dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Installation fehlgeschlagen!
        pause
        exit /b 1
    )
    echo.
    echo Installation erfolgreich!
)

python -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo.
    echo FEHLER: requests ist nicht installiert!
    echo Installiere Dependencies...
    pip install -r requirements.txt
)

echo.
echo Starte GUI...
echo.
python GitHubFollowerCheckerGUI.py

if errorlevel 1 (
    echo.
    echo ========================================
    echo   Fehler beim Starten der GUI!
    echo ========================================
    echo.
    pause
)
