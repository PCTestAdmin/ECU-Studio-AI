@echo off
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=py"
)
set "PYTHONPATH=%CD%\src"
%PY% -m pip install "scikit-learn>=1.6,<2" || goto :error
%PY% -m ecu_studio.recognition.train_structure_rejector --out src\ecu_studio\recognition\data\structure_rejector_v110.json --report TRAINING_REPORT_V110.json || goto :error
%PY% -m pytest -q tests\test_v110_training.py || goto :error
echo Training und synthetischer Test abgeschlossen. Keine reale ECU-/TCU-Validierung.
pause
exit /b 0
:error
echo Trainingslauf fehlgeschlagen. Vorheriges Modell bleibt nach Moeglichkeit erhalten.
pause
exit /b 1
