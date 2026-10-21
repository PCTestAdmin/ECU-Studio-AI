param([switch]$SkipTests, [string]$Python313 = '')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
# The portable package bundles the interpreter itself (python313.dll, python313._pth),
# so packaging needs exactly CPython 3.13 x64. It uses its own environment and
# leaves the development .venv (any supported version) alone.
$venv = Join-Path $PSScriptRoot '.venv-build'
$python = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    if ($Python313) {
        # CI passes the interpreter explicitly (actions/setup-python).
        & $Python313 -m venv $venv
    } else {
        & py -3.13 -c "import sys" 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw 'Für das portable Paket wird CPython 3.13 (64 Bit) benötigt: https://www.python.org/downloads/ – danach erneut starten.'
        }
        & py -3.13 -m venv $venv
    }
    if ($LASTEXITCODE -ne 0) { throw 'Build-Umgebung (.venv-build, Python 3.13) konnte nicht erstellt werden.' }
}
$check = & $python -c "import sys,struct;print(sys.version_info[:2]==(3,13) and struct.calcsize('P')==8)"
if ($check -ne 'True') {
    throw '.venv-build ist nicht CPython 3.13 x64. Ordner .venv-build löschen und erneut starten.'
}
& $python -m pip install -r requirements-lock-windows.txt
if ($LASTEXITCODE -ne 0) { throw 'Abhängigkeiten konnten nicht installiert werden.' }
& $python -m pip install --no-deps -e .
if ($LASTEXITCODE -ne 0) { throw 'Projekt konnte nicht installiert werden.' }
$env:QT_QPA_PLATFORM = 'offscreen'
$env:OPENBLAS_NUM_THREADS = '1'
if (-not $SkipTests) {
    & $python -m pytest -q --junitxml=.qa/tests.xml
    if ($LASTEXITCODE -ne 0) { throw 'Regressionstests fehlgeschlagen.' }
    & $python -m ecu_studio.tools.gui_smoke .qa/source-gui
    if ($LASTEXITCODE -ne 0) { throw 'GUI-Integration fehlgeschlagen.' }
}
& $python -m ecu_studio.tools.build_portable_runtime
if ($LASTEXITCODE -ne 0) { throw 'Windows-Build fehlgeschlagen.' }
$version = (& $python -c "import ecu_studio;print(ecu_studio.__version__)").Trim()
$executable = Join-Path $PSScriptRoot 'dist\ECU-Studio-AI\ECU-Studio-AI.exe'

function Invoke-Smoke([string]$exe, [string]$label) {
    $out = Join-Path ([System.IO.Path]::GetTempPath()) ('ECU-Studio-AI-smoke-' + [Guid]::NewGuid().ToString('N'))
    $started = Get-Date
    $p = Start-Process -FilePath $exe -ArgumentList @('--smoke-test', ('"' + $out + '"')) -WindowStyle Hidden -PassThru -Wait
    $report = Join-Path $out 'gui-smoke.json'
    if ($p.ExitCode -ne 0 -or -not (Test-Path $report)) { throw "Integrationstest der EXE fehlgeschlagen ($label)." }
    if ((Get-Item -LiteralPath $report).LastWriteTime -lt $started) { throw "Kein frischer EXE-Testbericht ($label)." }
    if (-not (Get-Content -LiteralPath $report -Raw | ConvertFrom-Json).passed) { throw "EXE-Prüfung meldet keinen Erfolg ($label)." }
    $check = Start-Process -FilePath $exe -ArgumentList '--self-check' -WindowStyle Hidden -PassThru -Wait
    if ($check.ExitCode -ne 0) { throw "Selbsttest (--self-check) fehlgeschlagen ($label)." }
    return $out
}

$smokeOutput = Invoke-Smoke $executable 'Build-Ordner'
$qaDestination = Join-Path $PSScriptRoot '.qa\exe-gui'
New-Item -ItemType Directory -Path $qaDestination -Force | Out-Null
Get-ChildItem -LiteralPath $smokeOutput | Copy-Item -Destination $qaDestination -Recurse -Force

# Release files: ZIP + SHA-256 (what users download and what the updater verifies).
& $python -m ecu_studio.tools.build_portable_runtime --package
if ($LASTEXITCODE -ne 0) { throw 'ZIP-Paket konnte nicht erstellt werden.' }
$archive = Join-Path $PSScriptRoot "dist\ECU-Studio-AI-$version-windows-x64.zip"

# The unpacked ZIP must start without any Python on the machine: run it with a PATH
# that contains only Windows itself and without Python variables.
$unpacked = Join-Path ([System.IO.Path]::GetTempPath()) ('ECU-Studio-AI-zip-' + [Guid]::NewGuid().ToString('N'))
Expand-Archive -LiteralPath $archive -DestinationPath $unpacked
$savedPath, $savedHome, $savedPythonPath = $env:PATH, $env:PYTHONHOME, $env:PYTHONPATH
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\WindowsPowerShell\v1.0"
    Remove-Item Env:PYTHONHOME, Env:PYTHONPATH -ErrorAction SilentlyContinue
    Invoke-Smoke (Join-Path $unpacked 'ECU-Studio-AI\ECU-Studio-AI.exe') 'entpacktes ZIP ohne Python im PATH' | Out-Null
} finally {
    $env:PATH = $savedPath
    if ($savedHome) { $env:PYTHONHOME = $savedHome }
    if ($savedPythonPath) { $env:PYTHONPATH = $savedPythonPath }
    Remove-Item -LiteralPath $unpacked -Recurse -Force -ErrorAction SilentlyContinue
}

# Optional classic installer (Inno Setup 6); skipped when ISCC is not installed.
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    # Build outside the project: Windows "controlled folder access" may stop ISCC from
    # writing executables into Documents; PowerShell then copies the finished file.
    $isccOut = Join-Path ([System.IO.Path]::GetTempPath()) ('ECU-Studio-AI-installer-' + [Guid]::NewGuid().ToString('N'))
    & $iscc /Qp "/O$isccOut" "/DAppVersion=$version" (Join-Path $PSScriptRoot 'packaging\installer.iss')
    if ($LASTEXITCODE -ne 0) { throw 'Installer konnte nicht erstellt werden.' }
    $setup = "ECU-Studio-AI-$version-setup.exe"
    Copy-Item -LiteralPath (Join-Path $isccOut $setup) -Destination (Join-Path $PSScriptRoot "dist\$setup") -Force
    Remove-Item -LiteralPath $isccOut -Recurse -Force
    $setupHash = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot "dist\$setup") -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath (Join-Path $PSScriptRoot "dist\$setup.sha256") -Value "$setupHash  $setup" -Encoding ascii
    Write-Host "Installer: dist\$setup"
} else {
    Write-Host 'Inno Setup 6 nicht gefunden – Installer übersprungen (ZIP-Paket ist vollständig).'
}
Get-FileHash -LiteralPath $archive -Algorithm SHA256 | Format-List
Write-Host "Windows-Paket: $archive (entpacken, ECU-Studio-AI.exe starten)."
