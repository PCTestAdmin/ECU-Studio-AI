@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe py -m venv .venv
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m pip install -e ".[dev]"
if errorlevel 1 exit /b 1
set QT_QPA_PLATFORM=offscreen
set OPENBLAS_NUM_THREADS=1
.venv\Scripts\python.exe -m pytest -q --junitxml=next-tests.xml
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m ecu_studio.tools.gui_smoke qa-artifacts\source-gui
exit /b %errorlevel%
