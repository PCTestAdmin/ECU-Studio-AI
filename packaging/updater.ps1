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

-Installer <setup.exe> (from 1.20.1, installations made with the installer):
instead of swapping folders, the verified setup of the new version runs silently
over the installation. Inno Setup then knows every program file (uninstall log),
updates its uninstaller and the version shown in "Apps & Features", and removes
unchanged files the new version no longer ships. Before that the program folder is
copied to <folder>.backup; if the setup, the version/inventory check or the
self-check fails, that copy is put back (exit 3).

After a ZIP update, a restore or a rollback the version in "Apps & Features"
(DisplayVersion/DisplayName of the Inno uninstall entry) is set to the installed
version, but only when that entry's InstallLocation is exactly this folder.

No folder is ever deleted as a whole unless THIS run created it and it is still
disposable (the unpacked staging folder, an incomplete backup copy); even then
links/junctions are not followed. A folder that already exists (<folder>.backup,
<folder>.update-staging) can hold the only copy of a file the user changed or
added. It is renamed to a free name "<name>.erhalten[-N]" first (no file changes):
- after a failure it is renamed back, so the old state is complete again;
- after success it is cleaned file by file by the installation's own
  _internal\uninstall_cleanup.ps1 -Mode Leftover (only unchanged inventory files,
  byte-identical copies and this application's uninstaller files go). What stays
  remains in "<name>.erhalten" and is logged. Without that script (or if it was
  changed) nothing is removed.
The failed new version of a rollback is moved to a free "<folder>.update-failed[-N]"
and cleaned the same way against the restored installation. An existing
.update-failed or .restore-swap folder is never reused or removed.
#>
param(
    [Parameter(Mandatory = $true)][string]$InstallDir,
    [string]$Archive = '',
    [string]$Sha256 = '',
    [int]$WaitPid = 0,
    [string]$LogFile = '',
    [string]$CheckArguments = '--self-check',
    [switch]$Relaunch,
    [switch]$Restore,
    [string]$Installer = '',
    [string]$ExpectedVersion = '',
    [string[]]$InstallerArguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOCANCEL', '/SP-'),
    # Inno Setup uninstall entry of the per-user installation (AppId in installer.iss); '' = do not touch.
    [string]$UninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{F8CD5330-FC90-4891-BFDA-58E6668C93A5}_is1'
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
# The UI launches this script with cwd=<LOCALAPPDATA>\ECUStudioAI\updates so the
# updater process never owns the installation directory while it is renamed.
# Move away defensively as well for direct invocations.
try { Set-Location -LiteralPath ([System.IO.Path]::GetTempPath()) } catch { }
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

$script:aside = [System.Collections.Generic.List[object]]::new()   # folders renamed by Move-Aside in this run
$script:own = [System.Collections.Generic.List[string]]::new()      # folders this run created and may still discard
$script:cleanupScript = ''                                          # verified copy of uninstall_cleanup.ps1

function Exit-Updater([int]$code) {
    if ($script:cleanupScript) { Remove-Item -LiteralPath $script:cleanupScript -Force -ErrorAction SilentlyContinue }
    exit $code
}

function Fail([int]$code, [string]$text) {
    Log ('FEHLER: ' + $text)
    # Only what this run created and is still disposable goes; renamed folders get their names back.
    foreach ($folder in @($script:own)) { Remove-OwnFolder $folder }
    Undo-Aside
    if ($code -ne 0 -and -not $env:ECU_UPDATER_QUIET) {
        try {
            Add-Type -AssemblyName System.Windows.Forms
            [System.Windows.Forms.MessageBox]::Show($text, 'ECU Studio AI – Update', 'OK', 'Error') | Out-Null
        } catch { }
    }
    Exit-Updater $code
}

function Rename-WithRetry([string]$path, [string]$newName, [int]$timeoutSeconds = 30) {
    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    $last = $null
    do {
        try {
            Rename-Item -LiteralPath $path -NewName $newName -ErrorAction Stop
            return
        } catch {
            $last = $_.Exception.Message
            Start-Sleep -Milliseconds 500
        }
    } while ((Get-Date) -lt $deadline)
    throw $last
}

function Get-FreeName([string]$path) {
    # $path itself if nothing exists there, else the first free "$path-N". Existing folders are never reused.
    if (-not (Test-Path -LiteralPath $path)) { return $path }
    for ($n = 2; $n -lt 1000; $n++) { if (-not (Test-Path -LiteralPath "$path-$n")) { return "$path-$n" } }
    throw "Kein freier Name für $path"
}

function Move-Aside([string]$path) {
    # A folder this run did not create is never deleted as a whole: it is renamed to a free name "<path>.erhalten[-N]"
    # (no file changes). Fail puts it back (Undo-Aside), success cleans it file by file (Clear-Aside). Throws if it
    # cannot be renamed (a file in it is open, no permission); it is then unchanged.
    if (-not (Test-Path -LiteralPath $path)) { return }
    $target = Get-FreeName ($path + '.erhalten')
    Rename-WithRetry $path (Split-Path $target -Leaf) 10
    if (Test-Path -LiteralPath $path) { throw "$path besteht nach dem Umbenennen weiter" }
    $script:aside.Add([pscustomobject]@{ Original = $path; Aside = $target })
    Log "Beiseitegelegt (nichts gelöscht): $path -> $target"
}

function Undo-Aside {
    # After a failure: renamed folders get their old names back (if free again), so the previous state is complete.
    for ($i = $script:aside.Count - 1; $i -ge 0; $i--) {
        $entry = $script:aside[$i]
        if ((Test-Path -LiteralPath $entry.Aside) -and -not (Test-Path -LiteralPath $entry.Original)) {
            try {
                Rename-WithRetry $entry.Aside (Split-Path $entry.Original -Leaf) 10
                Log "Zurückbenannt: $($entry.Aside) -> $($entry.Original)"
            } catch { Log "Bleibt unverändert unter $($entry.Aside): $($_.Exception.Message)" }
        } else { Log "Bleibt unverändert unter $($entry.Aside)" }
    }
    $script:aside.Clear()
}

function Remove-PlainTree([string]$folder) {
    foreach ($child in @(Get-ChildItem -LiteralPath $folder -Force)) {
        if ($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { Log "Behalten (Verweis/Junction): $($child.FullName)"; continue }
        if ($child.PSIsContainer) { Remove-PlainTree $child.FullName }
        else { Remove-Item -LiteralPath $child.FullName -Force -ErrorAction Stop }
    }
    if (@(Get-ChildItem -LiteralPath $folder -Force).Count -eq 0) { Remove-Item -LiteralPath $folder -Force -ErrorAction Stop }
}

function Remove-OwnFolder([string]$path) {
    # Only a folder THIS run created and registered in $script:own while it is still disposable: unpacked archive
    # content or copies of files that still exist in the installation. Links/junctions are neither followed nor removed.
    if (-not $script:own.Contains($path)) { Log "Nicht entfernt (nicht von diesem Lauf angelegt): $path"; return }
    [void]$script:own.Remove($path)
    if (-not (Test-Path -LiteralPath $path)) { return }
    try {
        if ((Get-Item -LiteralPath $path -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint) { Log "Nicht entfernt (Verweis): $path"; return }
        Remove-PlainTree $path
    } catch { Log "Ordner bleibt ($($_.Exception.Message)): $path" }
}

function Initialize-Cleanup {
    # The installation's own cleanup script (the uninstaller's rules), verified against the installation's inventory
    # and copied out, because the installation folder is renamed during the update. Missing or changed: no cleanup.
    $shipped = Join-Path $InstallDir '_internal\uninstall_cleanup.ps1'
    try {
        if (-not (Test-Path -LiteralPath $shipped -PathType Leaf)) { Log 'Bereinigungsskript fehlt: beiseitegelegte Ordner bleiben vollständig erhalten.'; return }
        $inventory = Get-Content -LiteralPath (Join-Path $InstallDir 'RUNTIME_INVENTORY.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $entry = @($inventory.files | Where-Object { $_.path -eq '_internal/uninstall_cleanup.ps1' }) | Select-Object -First 1
        $copy = Join-Path ([System.IO.Path]::GetTempPath()) ('ecu-studio-cleanup-' + [Guid]::NewGuid().ToString('N') + '.ps1')
        Copy-Item -LiteralPath $shipped -Destination $copy -ErrorAction Stop
        if (-not $entry -or (Get-Sha256 $copy) -ne ([string]$entry.sha256).ToLowerInvariant()) {
            Remove-Item -LiteralPath $copy -Force -ErrorAction SilentlyContinue
            Log 'Bereinigungsskript nicht im Inventar oder verändert: beiseitegelegte Ordner bleiben vollständig erhalten.'
            return
        }
        $script:cleanupScript = $copy
    } catch { Log ('Bereinigungsskript nicht nutzbar (' + $_.Exception.Message + '): beiseitegelegte Ordner bleiben vollständig erhalten.') }
}

function Invoke-Leftover([string]$folder, [string]$reference) {
    # File by file (uninstall_cleanup.ps1 -Mode Leftover): only unchanged inventory files, byte-identical copies of the
    # file at the same path in $reference and this application's uninstaller files go; the folder only when empty.
    if (-not (Test-Path -LiteralPath $folder -PathType Container)) { return }
    if (-not $script:cleanupScript) { Log "Nicht Datei für Datei geprüft, bleibt vollständig erhalten: $folder"; return }
    $arguments = @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $script:cleanupScript,
                   '-InstallDir', $folder, '-Mode', 'Leftover', '-Reference', $reference)
    if ($LogFile) { $arguments += @('-LogFile', $LogFile) }
    $ErrorActionPreference = 'Continue'      # stderr of the child must not end this script
    try {
        & (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') @arguments 2>&1 |
            ForEach-Object { if (-not $LogFile) { Write-Host "  $_" } }
        if ($LASTEXITCODE -ne 0) { Log "Bereinigung beendet mit Exit $LASTEXITCODE (nichts gelöscht): $folder" }
    } catch { Log "Bereinigung nicht ausgeführt ($($_.Exception.Message)): $folder" }
}

function Report-Kept([string]$folder) {
    if (Test-Path -LiteralPath $folder) {
        $count = @(Get-ChildItem -LiteralPath $folder -Recurse -File -Force -ErrorAction SilentlyContinue).Count
        Log "Erhalten (unbekannte oder veränderte Dateien, nichts davon gelöscht): $folder ($count Dateien)"
    }
}

function Clear-Aside {
    # After success: renamed folders are cleaned file by file; what stays is the user's and keeps its folder.
    foreach ($entry in @($script:aside)) {
        if ($entry.Original -eq $staging) {
            Invoke-Leftover (Join-Path $entry.Aside $PackageFolder) $InstallDir
            if ((Test-Path -LiteralPath $entry.Aside) -and @(Get-ChildItem -LiteralPath $entry.Aside -Force).Count -eq 0) {
                Remove-Item -LiteralPath $entry.Aside -Force      # empty folder only
            }
        } else {
            $reference = if (Test-Path -LiteralPath $backup) { $backup } else { $InstallDir }
            Invoke-Leftover $entry.Aside $reference
        }
        Report-Kept $entry.Aside
    }
    $script:aside.Clear()
}

function Restore-Previous {
    # Rollback: the failed new version moves to a FREE "<folder>.update-failed[-N]", the backup takes its place again,
    # then the failed folder is cleaned file by file against the restored installation (its user files are copies).
    $failed = Get-FreeName ($InstallDir + '.update-failed')
    $moved = $false
    try {
        if (Test-Path -LiteralPath $InstallDir) { Rename-WithRetry $InstallDir (Split-Path $failed -Leaf); $moved = $true }
        Rename-WithRetry $backup (Split-Path $InstallDir -Leaf)
    } catch {
        if ($moved -and -not (Test-Path -LiteralPath $InstallDir)) { try { Rename-WithRetry $failed (Split-Path $InstallDir -Leaf) } catch { } }
        Fail 4 ('Rollback fehlgeschlagen; vorherige Version liegt in ' + $backup)
    }
    if ($moved) { Invoke-Leftover $failed $InstallDir; Report-Kept $failed }
}

function Get-UninstallEntry {
    # The Inno uninstall entry if it belongs to THIS folder, else $null (other copy, portable, tests).
    if (-not $UninstallKey -or -not (Test-Path -LiteralPath $UninstallKey)) { return $null }
    try { $entry = Get-ItemProperty -LiteralPath $UninstallKey -ErrorAction Stop } catch { return $null }
    $location = [string]$entry.InstallLocation
    if (-not $location) { return $null }
    try { $location = [System.IO.Path]::GetFullPath($location.TrimEnd('\')) } catch { return $null }
    if ($location -ne $InstallDir) { return $null }      # -ne is case-insensitive
    return $entry
}

function Sync-UninstallEntry {
    # Keep "Apps & Features" in line with the version that is actually installed.
    if ($null -eq (Get-UninstallEntry)) { return }
    try {
        $version = (Get-Content -LiteralPath (Join-Path $InstallDir 'VERSION.txt') -Raw).Trim()
        if ($version -notmatch '^\d+\.\d+\.\d+$') { return }
        Set-ItemProperty -LiteralPath $UninstallKey -Name 'DisplayVersion' -Value $version
        Set-ItemProperty -LiteralPath $UninstallKey -Name 'DisplayName' -Value "ECU Studio AI $version"
        Log ('Versionsanzeige in Apps & Features: ' + $version)
    } catch { Log ('Versionsanzeige nicht angepasst: ' + $_.Exception.Message) }
}

function Get-InventoryProblem([string]$folder) {
    # First file of RUNTIME_INVENTORY.json that is missing or differs, $null when all match.
    $path = Join-Path $folder 'RUNTIME_INVENTORY.json'
    if (-not (Test-Path -LiteralPath $path)) { return 'RUNTIME_INVENTORY.json fehlt' }
    $inventory = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($entry in $inventory.files) {
        $file = Join-Path $folder ($entry.path -replace '/', '\')
        if (-not (Test-Path -LiteralPath $file)) { return "fehlt: $($entry.path)" }
        if ((Get-Sha256 $file) -ne $entry.sha256) { return "abweichend: $($entry.path)" }
    }
    return $null
}

$InstallDir = [System.IO.Path]::GetFullPath($InstallDir.TrimEnd('\'))
$backup = $InstallDir + '.backup'
$staging = $InstallDir + '.update-staging'
if ($Restore) { Log "Wiederherstellung gestartet: $backup -> $InstallDir" }
elseif ($Installer) {
    if (-not $Sha256) { Fail 2 'Sha256 ist für ein Update per Installer erforderlich.' }
    Log "Update per Installer gestartet: $Installer -> $InstallDir"
}
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
    try { $swap = Get-FreeName ($InstallDir + '.restore-swap') }     # an existing one is never reused or removed
    catch { Fail 2 ('Wiederherstellung nicht möglich: ' + $_.Exception.Message) }
    try {
        Rename-WithRetry $InstallDir (Split-Path $swap -Leaf)
        Rename-WithRetry $backup (Split-Path $InstallDir -Leaf)
        Rename-WithRetry $swap (Split-Path $backup -Leaf)
    } catch {
        if ((Test-Path -LiteralPath $swap) -and -not (Test-Path -LiteralPath $InstallDir)) { Rename-WithRetry $swap (Split-Path $InstallDir -Leaf) }
        Fail 2 ('Wiederherstellung nicht möglich (Ordner in Benutzung?): ' + $_.Exception.Message)
    }
    if (-not (Test-Start $InstallDir)) {
        Log 'Wiederhergestellte Version startet nicht – zurück zur vorherigen Installation.'
        try {
            Rename-WithRetry $InstallDir (Split-Path $swap -Leaf)
            Rename-WithRetry $backup (Split-Path $InstallDir -Leaf)
            Rename-WithRetry $swap (Split-Path $backup -Leaf)
        } catch { Fail 4 ('Zurücktauschen fehlgeschlagen; Versionen liegen in ' + $InstallDir + ' und ' + $backup) }
        Sync-UninstallEntry
        Fail 3 'Die gesicherte Version startete nicht – die bisherige Version bleibt aktiv.'
    }
    Log "Vorherige Version wiederhergestellt; die ersetzte Version liegt jetzt in $backup."
    Sync-UninstallEntry
    if ($Relaunch) { Start-Process -FilePath (Join-Path $InstallDir $ExeName) -WorkingDirectory $InstallDir | Out-Null }
    Exit-Updater 0
}

Initialize-Cleanup

if ($Installer) {
    # Installer route: only for an installation registered by the installer for exactly this folder.
    if (-not (Test-Path -LiteralPath (Join-Path $InstallDir 'unins000.exe'))) { Fail 2 'Keine Installer-Installation (unins000.exe fehlt) – nichts wurde verändert.' }
    if ($UninstallKey -and $null -eq (Get-UninstallEntry)) { Fail 2 'Die Windows-Installation gehört zu einem anderen Ordner – nichts wurde verändert.' }
    if (-not (Test-Path -LiteralPath $Installer -PathType Leaf)) { Fail 2 "Installer fehlt: $Installer" }
    if ((Get-Sha256 $Installer) -ne $Sha256.ToLowerInvariant()) { Fail 2 'Prüfsumme des Installers stimmt nicht – nichts wurde verändert.' }
    $installerSignature = (Get-AuthenticodeSignature -LiteralPath $Installer).Status
    if ($installerSignature -eq 'Valid') { Log 'Installer-Signatur gültig.' }
    elseif ($installerSignature -eq 'NotSigned') { Log 'Installer ist nicht signiert (Integrität per SHA-256 geprüft).' }
    else { Fail 2 ('Signatur des Installers ungültig: ' + $installerSignature) }

    # Backup copy: the setup needs the folder in place, so copy instead of renaming. An existing backup is moved
    # aside, never deleted; the new copy is this run's own and disposable until it is complete.
    try { Move-Aside $backup }
    catch { Fail 2 ('Vorhandene Sicherung ' + $backup + ' lässt sich nicht beiseitelegen (Datei geöffnet?) – nichts wurde verändert: ' + $_.Exception.Message) }
    if (Test-Path -LiteralPath $backup) { Fail 2 "Sicherungsordner $backup ist belegt – nichts wurde verändert." }
    $script:own.Add($backup)
    try {
        Copy-Item -LiteralPath $InstallDir -Destination $backup -Recurse -Force -ErrorAction Stop
        $before = @(Get-ChildItem -LiteralPath $InstallDir -Recurse -File -Force).Count
        $copied = @(Get-ChildItem -LiteralPath $backup -Recurse -File -Force).Count
        if ($before -ne $copied) { throw "Sicherung unvollständig ($copied von $before Dateien)" }
    } catch {
        Fail 2 ('Sicherung der Installation nicht möglich – nichts wurde verändert: ' + $_.Exception.Message)
    }
    [void]$script:own.Remove($backup)                   # complete: from now on the copy is the way back, never discarded
    Log "Sicherung angelegt: $backup"

    $setupLog = if ($LogFile) { [System.IO.Path]::ChangeExtension($LogFile, '.setup.log') } else { Join-Path ([System.IO.Path]::GetTempPath()) 'ECU-Studio-AI-setup.log' }
    $arguments = @($InstallerArguments) + @(('/DIR="' + $InstallDir + '"'), ('/LOG="' + $setupLog + '"'))
    $problem = $null
    try {
        $setup = Start-Process -FilePath $Installer -ArgumentList $arguments -PassThru -Wait -WindowStyle Hidden
        if ($setup.ExitCode -ne 0) { $problem = "Installer beendet mit Exit $($setup.ExitCode) (Protokoll: $setupLog)" }
    } catch { $problem = 'Installer konnte nicht gestartet werden: ' + $_.Exception.Message }
    if (-not $problem -and $ExpectedVersion) {
        $installed = (Get-Content -LiteralPath (Join-Path $InstallDir 'VERSION.txt') -Raw -ErrorAction SilentlyContinue)
        if (-not $installed -or $installed.Trim() -ne $ExpectedVersion) { $problem = "Nach dem Installer falsche Version: $installed" }
    }
    if (-not $problem) { $bad = Get-InventoryProblem $InstallDir; if ($bad) { $problem = "Installation unvollständig ($bad)" } }
    if (-not $problem -and -not (Test-Start $InstallDir)) { $problem = 'Selbsttest der neuen Version fehlgeschlagen' }
    if ($problem) {
        Log ($problem + ' – Rollback.')
        Restore-Previous
        Sync-UninstallEntry
        Fail 3 ('Das Update wurde nicht installiert – die vorherige Version wurde wiederhergestellt. ' + $problem)
    }
    Log "Update per Installer installiert; vorherige Version bleibt als Sicherung in $backup."
    Clear-Aside
    if ($Relaunch) { Start-Process -FilePath (Join-Path $InstallDir $ExeName) -WorkingDirectory $InstallDir | Out-Null }
    Exit-Updater 0
}

# 2. Archive integrity.
$actual = Get-Sha256 $Archive
if ($actual -ne $Sha256.ToLowerInvariant()) { Fail 2 'Prüfsumme des Update-Pakets stimmt nicht – nichts wurde verändert.' }

# 3. Unpack into staging: an existing staging folder (interrupted update) is moved aside, never deleted; the new one
#    is this run's own and disposable until the new version is in place.
try { Move-Aside $staging }
catch { Fail 2 ('Vorhandener Ordner ' + $staging + ' lässt sich nicht beiseitelegen (Datei geöffnet?) – nichts wurde verändert: ' + $_.Exception.Message) }
if (Test-Path -LiteralPath $staging) { Fail 2 "Ordner $staging ist belegt – nichts wurde verändert." }
$script:own.Add($staging)
try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($Archive, $staging)
} catch { Fail 2 ('Update-Paket konnte nicht entpackt werden: ' + $_.Exception.Message) }
$new = Join-Path $staging $PackageFolder
$inventoryPath = Join-Path $new 'RUNTIME_INVENTORY.json'
if (-not (Test-Path -LiteralPath (Join-Path $new $ExeName)) -or -not (Test-Path -LiteralPath $inventoryPath)) {
    Fail 2 'Update-Paket hat nicht den erwarteten Aufbau.'
}

# 4. Per-file verification and signature.
$inventory = Get-Content -LiteralPath $inventoryPath -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($entry in $inventory.files) {
    $file = Join-Path $new ($entry.path -replace '/', '\')
    if (-not (Test-Path -LiteralPath $file)) { Fail 2 "Datei fehlt im Update: $($entry.path)" }
    if ((Get-Sha256 $file) -ne $entry.sha256) { Fail 2 "Datei im Update beschädigt: $($entry.path)" }
}
$signature = Get-AuthenticodeSignature -LiteralPath (Join-Path $new $ExeName)
if ($signature.Status -eq 'Valid') { Log ('Signatur gültig: ' + $signature.SignerCertificate.Subject) }
elseif ($signature.Status -eq 'NotSigned') { Log 'EXE ist nicht signiert (Integrität per SHA-256 geprüft).' }
else { Fail 2 ('Signatur der neuen EXE ungültig: ' + $signature.Status) }

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

# 6. Swap with backup: an existing backup is moved aside, never deleted (it is put back if the update fails).
try { Move-Aside $backup }
catch { Fail 2 ('Vorhandene Sicherung ' + $backup + ' lässt sich nicht beiseitelegen (Datei geöffnet?) – nichts wurde verändert: ' + $_.Exception.Message) }
try { Rename-WithRetry $InstallDir (Split-Path $backup -Leaf) }
catch { Fail 2 ('Installation ist in Benutzung oder schreibgeschützt: ' + $_.Exception.Message) }
try {
    Move-Item -LiteralPath $new -Destination $InstallDir
} catch {
    Log ('Einsetzen fehlgeschlagen: ' + $_.Exception.Message)
    Restore-Previous
    Fail 3 'Update konnte nicht eingesetzt werden – die vorherige Version wurde wiederhergestellt.'
}
Remove-OwnFolder $staging                               # now empty: the new version was moved out of it

# 7. Self-check of the new version; roll back on failure.
$exe = Join-Path $InstallDir $ExeName
if (-not (Test-Start $InstallDir)) {
    Log 'Selbsttest der neuen Version fehlgeschlagen – Rollback.'
    Restore-Previous
    Fail 3 'Die neue Version startete nicht korrekt – die vorherige Version wurde wiederhergestellt.'
}
Log "Update installiert; vorherige Version bleibt als Sicherung in $backup."
Clear-Aside
Sync-UninstallEntry

# 8. Start the new version.
if ($Relaunch) { Start-Process -FilePath $exe -WorkingDirectory $InstallDir | Out-Null }
Exit-Updater 0
