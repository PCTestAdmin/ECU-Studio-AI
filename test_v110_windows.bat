@echo off
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=py"
)
set "PYTHONPATH=%CD%\src"
%PY% -m pytest -q
if errorlevel 1 goto :error
%PY% -m ecu_studio.tools.firmware_holdout eval --manifest examples\holdout_synthetic_tcu_manifest.json --out examples\HOLDOUT_SYNTHETIC_V19_REPORT.json
if errorlevel 1 goto :error
echo Tests abgeschlossen. Synthetische Erkennung ist kein ECU-Freigabenachweis.
pause
exit /b 0
:error
pause
exit /b 1
