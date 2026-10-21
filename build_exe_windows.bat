@echo off
setlocal
cd /d "%~dp0"
rem Packaging needs CPython 3.13 x64; build_release.ps1 creates .venv-build itself.
powershell -NoProfile -ExecutionPolicy Bypass -File build_release.ps1 || goto :error
echo Portables Paket: dist\ECU-Studio-AI-*-windows-x64.zip (Ordner dist\ECU-Studio-AI)
pause
exit /b 0
:error
pause
exit /b 1
