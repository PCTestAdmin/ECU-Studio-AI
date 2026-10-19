@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Bitte zuerst start_windows.bat ausfuehren.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install pyinstaller || goto :error
powershell -NoProfile -ExecutionPolicy Bypass -File build_release.ps1 || goto :error
echo EXE liegt in dist\ECU-Studio-AI-1.11\
pause
exit /b 0
:error
pause
exit /b 1
