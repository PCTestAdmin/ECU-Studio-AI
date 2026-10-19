param([switch]$SkipTests)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    & py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python-Umgebung konnte nicht erstellt werden.' }
}
& $python -m pip install -r requirements-lock-windows.txt
if ($LASTEXITCODE -ne 0) { throw 'Abhängigkeiten konnten nicht installiert werden.' }
& $python -m pip install --no-deps -e .
if ($LASTEXITCODE -ne 0) { throw 'Projekt konnte nicht installiert werden.' }
$env:QT_QPA_PLATFORM = 'offscreen'
$env:OPENBLAS_NUM_THREADS = '1'
if (-not $SkipTests) {
    & $python -m pytest -q --junitxml=.qa/v114-tests.xml
    if ($LASTEXITCODE -ne 0) { throw 'Regressionstests fehlgeschlagen.' }
    & $python -m ecu_studio.tools.gui_smoke .qa/v114-source-gui
    if ($LASTEXITCODE -ne 0) { throw 'GUI-Integration fehlgeschlagen.' }
}
& $python -m ecu_studio.tools.build_portable_runtime
if ($LASTEXITCODE -ne 0) { throw 'Windows-Build fehlgeschlagen.' }
$executable = Join-Path $PSScriptRoot 'dist\ECU-Studio-AI-1.14-portable\ECU-Studio-AI-1.14.exe'
$smokeOutput = Join-Path ([System.IO.Path]::GetTempPath()) ('ECU-Studio-AI-v114-smoke-' + [Guid]::NewGuid().ToString('N'))
$smokeStarted = Get-Date
$process = Start-Process -FilePath $executable -ArgumentList @('--smoke-test', ('"' + $smokeOutput + '"')) -WindowStyle Hidden -PassThru -Wait
$smokeReport = Join-Path $smokeOutput 'gui-smoke.json'
if ($process.ExitCode -ne 0 -or -not (Test-Path $smokeReport)) {
    throw 'Integrationstest der paketierten EXE fehlgeschlagen.'
}
if ((Get-Item -LiteralPath $smokeReport).LastWriteTime -lt $smokeStarted) { throw 'Kein frischer EXE-Testbericht.' }
$report = Get-Content -LiteralPath (Join-Path $smokeOutput 'gui-smoke.json') -Raw | ConvertFrom-Json
if (-not $report.passed) { throw 'EXE-Prüfung meldet keinen Erfolg.' }
$qaDestination = Join-Path $PSScriptRoot '.qa\v114-exe-gui'
New-Item -ItemType Directory -Path $qaDestination -Force | Out-Null
Get-ChildItem -LiteralPath $smokeOutput | Copy-Item -Destination $qaDestination -Recurse -Force
Get-FileHash -LiteralPath $executable -Algorithm SHA256 | Format-List
Write-Host 'Windows-Paket: dist\ECU-Studio-AI-1.14-portable (gesamten Ordner weitergeben).'
