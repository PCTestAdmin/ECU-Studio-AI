@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher "py" nicht gefunden. Bitte Python 3.10+ installieren.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  echo Erstelle Python-Umgebung...
  py -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat
python -m pip install -e . || goto :error
python -m ecu_studio.main
if errorlevel 1 (
  echo ECU Studio konnte nicht gestartet werden. Fehlermeldung oben beachten.
  pause
  exit /b 1
)
exit /b 0
:error
echo.
echo Fehler beim Einrichten oder Starten. Internetzugang beim ersten Start noetig.
pause
exit /b 1
