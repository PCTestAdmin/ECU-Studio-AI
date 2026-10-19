@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Bitte zuerst start_windows.bat ausfuehren.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File build_release.ps1 || goto :error
echo Portables Paket liegt in dist\ECU-Studio-AI-1.14-portable\
pause
exit /b 0
:error
pause
exit /b 1
