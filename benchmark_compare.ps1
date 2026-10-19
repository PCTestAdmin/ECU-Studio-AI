$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$python=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$archive=Join-Path (Split-Path $PSScriptRoot -Parent) 'ECU-Studio-AI-v1.10-original.zip'
$baseline=Join-Path $PSScriptRoot '.qa\reproduce-v110'
if (-not (Test-Path -LiteralPath $archive)) { throw 'Originalarchiv neben dem Projekt fehlt.' }
if (-not (Test-Path -LiteralPath $python)) { throw 'Zuerst test_next_windows.bat ausführen.' }
if (-not (Test-Path -LiteralPath (Join-Path $baseline 'src'))) {
    Expand-Archive -LiteralPath $archive -DestinationPath $baseline
}
foreach ($name in @('benchmark_next.py','detection_snapshot.py')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot ('src\ecu_studio\tools\'+$name)) -Destination (Join-Path $baseline ('src\ecu_studio\tools\'+$name))
}
$previousPythonPath=$env:PYTHONPATH
try {
    $env:QT_QPA_PLATFORM='offscreen'
    $env:OPENBLAS_NUM_THREADS='1'
    $env:PYTHONPATH=Join-Path $baseline 'src'
    & $python -m ecu_studio.tools.benchmark_next --out baseline-performance.json --repeats 3
    if ($LASTEXITCODE -ne 0) { throw 'Baseline-Benchmark fehlgeschlagen.' }
    & $python -m ecu_studio.tools.detection_snapshot --out baseline-detections.json
    if ($LASTEXITCODE -ne 0) { throw 'Baseline-Detektorsnapshot fehlgeschlagen.' }
    $env:PYTHONPATH=Join-Path $PSScriptRoot 'src'
    & $python -m ecu_studio.tools.benchmark_next --out next-performance.json --repeats 3
    if ($LASTEXITCODE -ne 0) { throw 'Aktueller Benchmark fehlgeschlagen.' }
    & $python -m ecu_studio.tools.detection_snapshot --out next-detections.json
    if ($LASTEXITCODE -ne 0) { throw 'Aktueller Detektorsnapshot fehlgeschlagen.' }
} finally {
    $env:PYTHONPATH=$previousPythonPath
}
