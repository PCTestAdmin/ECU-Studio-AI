<#
ECU Studio AI updater. Runs from a copy outside the install folder after the
application has closed (it never overwrites a running EXE).

1. wait for the application process to end
2. verify the archive SHA-256 again (it was checked after download)
3. unpack into a staging folder next to the installation
4. verify every file against RUNTIME_INVENTORY.json and the Authenticode
   signature of the new EXE when it is signed (a broken signature aborts)
5. keep files the user added to the installation
6. rename the installation to <folder>.backup, move the new version in place
7. run "ECU-Studio-AI.exe --self-check"; on failure restore the backup
8. start the new version (optional)

Projects and settings live outside the installation (%USERPROFILE%\.ecu_studio_ai,
registry) and are not touched. Exit codes: 0 updated, 2 verification failed
(nothing changed), 3 install failed and was rolled back, 4 rollback failed.

-Restore swaps the installation with <folder>.backup instead (the previous
version; afterwards the replaced version is the new backup), runs the same
self-check and swaps back if the restored version does not start.
#>
param(
    [Parameter(Mandatory = $true)][string]$InstallDir,
    [string]$Archive = '',
    [string]$Sha256 = '',
    [int]$WaitPid = 0,
    [string]$LogFile = '',
    [string]$CheckArguments = '--self-check',
    [switch]$Relaunch,
    [switch]$Restore
)
$ErrorActionPreference = 'Stop'
# Windows PowerShell started from a PowerShell 7 session inherits PSModulePath and may then
# load PS7 modules that cannot work here ("Get-FileHash is not recognized"). Use only the
# built-in Windows PowerShell modules.
if ($PSVersionTable.PSEdition -ne 'Core') {
    $env:PSModulePath = "$env:ProgramFiles\WindowsPowerShell\Modules;$PSHOME\Modules"
    foreach ($module in 'Microsoft.PowerShell.Management', 'Microsoft.PowerShell.Utility', 'Microsoft.PowerShell.Security') {
        Import-Module "$PSHOME\Modules\$module" -ErrorAction SilentlyContinue
    }
}
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ExeName = 'ECU-Studio-AI.exe'
$PackageFolder = 'ECU-Studio-AI'

function Get-Sha256([string]$path) {
    # .NET directly: no dependency on the Get-FileHash cmdlet/module.
    $stream = [System.IO.File]::OpenRead($path)
    try {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        return ([System.BitConverter]::ToString($sha.ComputeHash($stream)) -replace '-', '').ToLowerInvariant()
    } finally { $stream.Dispose() }
}

function Log([string]$text) {
    $line = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '  ' + $text
    if ($LogFile) { Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8 }
    Write-Host $line
}

function Fail([int]$code, [string]$text) {
    Log ('FEHLER: ' + $text)
    if ($code -ne 0 -and -not $env:ECU_UPDATER_QUIET) {
        try {
            Add-Type -AssemblyName System.Windows.Forms
            [System.Windows.Forms.MessageBox]::Show($text, 'ECU Studio AI – Update', 'OK', 'Error') | Out-Null
        } catch { }
    }
    exit $code
}

$InstallDir = [System.IO.Path]::GetFullPath($InstallDir.TrimEnd('\'))
$backup = $InstallDir + '.backup'
$staging = $InstallDir + '.update-staging'
if ($Restore) { Log "Wiederherstellung gestartet: $backup -> $InstallDir" }
elseif (-not $Archive -or -not $Sha256) { Fail 2 'Archive und Sha256 sind für ein Update erforderlich.' }
else { Log "Update gestartet: $Archive -> $InstallDir" }

# 1. Wait for the running application to end.
if ($WaitPid -gt 0) {
    $deadline = (Get-Date).AddSeconds(120)
    while ((Get-Process -Id $WaitPid -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 300 }
    if (Get-Process -Id $WaitPid -ErrorAction SilentlyContinue) { Fail 2 'ECU Studio AI läuft noch – Update nicht installiert.' }
}
if (-not (Test-Path -LiteralPath (Join-Path $InstallDir $ExeName))) { Fail 2 "Keine Installation gefunden in $InstallDir." }

function Test-Start([string]$folder) {
    $p = Start-Process -FilePath (Join-Path $folder $ExeName) -ArgumentList $CheckArguments -PassThru -WindowStyle Hidden
    $ok = $p.WaitForExit(180000) -and $p.ExitCode -eq 0
    if (-not $ok) { try { $p.Kill() } catch { } }
    return $ok
}

if ($Restore) {
    if (-not (Test-Path -LiteralPath (Join-Path $backup $ExeName))) { Fail 2 'Keine Sicherung einer vorherigen Version vorhanden.' }
    $swap = $InstallDir + '.restore-swap'
    if (Test-Path -LiteralPath $swap) { Remove-Item -LiteralPath $swap -Recurse -Force }
    try {
        Rename-Item -LiteralPath $InstallDir -NewName (Split-Path $swap -Leaf)
        Rename-Item -LiteralPath $backup -NewName (Split-Path $InstallDir -Leaf)
        Rename-Item -LiteralPath $swap -NewName (Split-Path $backup -Leaf)
    } catch {
        if ((Test-Path -LiteralPath $swap) -and -not (Test-Path -LiteralPath $InstallDir)) { Rename-Item -LiteralPath $swap -NewName (Split-Path $InstallDir -Leaf) }
        Fail 2 ('Wiederherstellung nicht möglich (Ordner in Benutzung?): ' + $_.Exception.Message)
    }
    if (-not (Test-Start $InstallDir)) {
        Log 'Wiederhergestellte Version startet nicht – zurück zur vorherigen Installation.'
        try {
            Rename-Item -LiteralPath $InstallDir -NewName (Split-Path $swap -Leaf)
            Rename-Item -LiteralPath $backup -NewName (Split-Path $InstallDir -Leaf)
            Rename-Item -LiteralPath $swap -NewName (Split-Path $backup -Leaf)
        } catch { Fail 4 ('Zurücktauschen fehlgeschlagen; Versionen liegen in ' + $InstallDir + ' und ' + $backup) }
        Fail 3 'Die gesicherte Version startete nicht – die bisherige Version bleibt aktiv.'
    }
    Log "Vorherige Version wiederhergestellt; die ersetzte Version liegt jetzt in $backup."
    if ($Relaunch) { Start-Process -FilePath (Join-Path $InstallDir $ExeName) -WorkingDirectory $InstallDir | Out-Null }
    exit 0
}

# 2. Archive integrity.
$actual = Get-Sha256 $Archive
if ($actual -ne $Sha256.ToLowerInvariant()) { Fail 2 'Prüfsumme des Update-Pakets stimmt nicht – nichts wurde verändert.' }

# 3. Unpack into staging.
if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($Archive, $staging)
} catch { Fail 2 ('Update-Paket konnte nicht entpackt werden: ' + $_.Exception.Message) }
$new = Join-Path $staging $PackageFolder
$inventoryPath = Join-Path $new 'RUNTIME_INVENTORY.json'
if (-not (Test-Path -LiteralPath (Join-Path $new $ExeName)) -or -not (Test-Path -LiteralPath $inventoryPath)) {
    Remove-Item -LiteralPath $staging -Recurse -Force
    Fail 2 'Update-Paket hat nicht den erwarteten Aufbau.'
}

# 4. Per-file verification and signature.
$inventory = Get-Content -LiteralPath $inventoryPath -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($entry in $inventory.files) {
    $file = Join-Path $new ($entry.path -replace '/', '\')
    if (-not (Test-Path -LiteralPath $file)) { Remove-Item -LiteralPath $staging -Recurse -Force; Fail 2 "Datei fehlt im Update: $($entry.path)" }
    if ((Get-Sha256 $file) -ne $entry.sha256) {
        Remove-Item -LiteralPath $staging -Recurse -Force; Fail 2 "Datei im Update beschädigt: $($entry.path)"
    }
}
$signature = Get-AuthenticodeSignature -LiteralPath (Join-Path $new $ExeName)
if ($signature.Status -eq 'Valid') { Log ('Signatur gültig: ' + $signature.SignerCertificate.Subject) }
elseif ($signature.Status -eq 'NotSigned') { Log 'EXE ist nicht signiert (Integrität per SHA-256 geprüft).' }
else { Remove-Item -LiteralPath $staging -Recurse -Force; Fail 2 ('Signatur der neuen EXE ungültig: ' + $signature.Status) }

# 5. Keep files the user added to the old installation.
$oldInventoryPath = Join-Path $InstallDir 'RUNTIME_INVENTORY.json'
$shipped = @{}
if (Test-Path -LiteralPath $oldInventoryPath) {
    (Get-Content -LiteralPath $oldInventoryPath -Raw -Encoding UTF8 | ConvertFrom-Json).files | ForEach-Object { $shipped[$_.path] = $true }
}
Get-ChildItem -LiteralPath $InstallDir -Recurse -File | ForEach-Object {
    $relative = $_.FullName.Substring($InstallDir.Length + 1) -replace '\\', '/'
    if (-not $shipped.ContainsKey($relative) -and $relative -notmatch '(^|/)__pycache__/' -and $relative -ne 'RUNTIME_INVENTORY.json') {
        $target = Join-Path $new ($relative -replace '/', '\')
        if (-not (Test-Path -LiteralPath $target)) {
            New-Item -ItemType Directory -Path (Split-Path $target) -Force | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $target
            Log "Eigene Datei übernommen: $relative"
        }
    }
}

# 6. Swap with backup.
if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
try { Rename-Item -LiteralPath $InstallDir -NewName (Split-Path $backup -Leaf) }
catch { Remove-Item -LiteralPath $staging -Recurse -Force; Fail 2 ('Installation ist in Benutzung oder schreibgeschützt: ' + $_.Exception.Message) }
try {
    Move-Item -LiteralPath $new -Destination $InstallDir
    Remove-Item -LiteralPath $staging -Recurse -Force
} catch {
    Log ('Einsetzen fehlgeschlagen: ' + $_.Exception.Message)
    if (Test-Path -LiteralPath $InstallDir) { Remove-Item -LiteralPath $InstallDir -Recurse -Force }
    Rename-Item -LiteralPath $backup -NewName (Split-Path $InstallDir -Leaf)
    Fail 3 'Update konnte nicht eingesetzt werden – die vorherige Version wurde wiederhergestellt.'
}

# 7. Self-check of the new version; roll back on failure.
$exe = Join-Path $InstallDir $ExeName
if (-not (Test-Start $InstallDir)) {
    Log 'Selbsttest der neuen Version fehlgeschlagen – Rollback.'
    try {
        Remove-Item -LiteralPath $InstallDir -Recurse -Force
        Rename-Item -LiteralPath $backup -NewName (Split-Path $InstallDir -Leaf)
    } catch { Fail 4 ('Rollback fehlgeschlagen; vorherige Version liegt in ' + $backup) }
    Fail 3 'Die neue Version startete nicht korrekt – die vorherige Version wurde wiederhergestellt.'
}
Log "Update installiert; vorherige Version bleibt als Sicherung in $backup."

# 8. Start the new version.
if ($Relaunch) { Start-Process -FilePath $exe -WorkingDirectory $InstallDir | Out-Null }
exit 0
