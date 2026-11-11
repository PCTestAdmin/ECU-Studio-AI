<#
ECU Studio AI: removes program files by inventory, never by pattern.

Used by the Inno Setup installer/uninstaller (packaging/installer.iss, from 1.20.1 on):

  -Mode Uninstall  before the uninstaller processes its own log: removes every file of
                   <InstallDir>\RUNTIME_INVENTORY.json. That also covers files an in-app
                   update added after the last installer run, which the uninstall log
                   does not know (finding A5 of release 1.20.0).
  -Mode Obsolete   after an installation over an existing one: removes files of the
                   PREVIOUS inventory (-Inventory) that the new version no longer ships
                   (-Keep = the new inventory).

A file is removed only if ALL of this holds:
  - it is listed in the inventory with a relative path (no drive, no root, no '..' or '.'
    segment, no ':' / wildcard characters),
  - its normalised full path lies inside the program folder,
  - neither the file nor any folder between it and the program folder is a reparse point
    (junction, symbolic link, mount point),
  - its SHA-256 equals the inventory value (changed files are the user's and stay).
Afterwards only EMPTY folders on the way to removed files are deleted, never the program
folder itself. Unlisted files (user files, unins000.*, logs) are never touched.
Anything doubtful keeps the file and is logged. Unreadable inventory: nothing is deleted.
Exit code 0 also when files were kept; 2 = invalid call, nothing deleted.
-WhatIf lists what would be removed without removing anything.
#>
param(
    [Parameter(Mandatory = $true)][string]$InstallDir,
    [ValidateSet('Uninstall', 'Obsolete')][string]$Mode = 'Uninstall',
    [string]$Inventory = '',
    [string]$Keep = '',
    [string]$LogFile = '',
    [switch]$WhatIf
)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core') {
    $env:PSModulePath = "$env:ProgramFiles\WindowsPowerShell\Modules;$PSHOME\Modules"
}
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { Set-Location -LiteralPath ([System.IO.Path]::GetTempPath()) } catch { }

$ReparsePoint = [System.IO.FileAttributes]::ReparsePoint
$script:removed = 0; $script:kept = 0

function Log([string]$text) {
    $line = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '  ' + $text
    if ($LogFile) { try { Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8 } catch { } }
    Write-Host $line
}

function Stop-Invalid([string]$text) { Log ('ABBRUCH (nichts gelöscht): ' + $text); exit 2 }

function Get-Sha256([string]$path) {
    $stream = [System.IO.File]::Open($path, 'Open', 'Read', 'Read')
    try {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        return ([System.BitConverter]::ToString($sha.ComputeHash($stream)) -replace '-', '').ToLowerInvariant()
    } finally { $stream.Dispose() }
}

function Read-Inventory([string]$path) {
    # Returns @{ 'relative\path' (lower case) = @{ Path = 'relative\path'; Sha256 = '...' } } or $null.
    if (-not $path -or -not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    try { $data = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json } catch { return $null }
    if ($null -eq $data -or $data.format -ne 1 -or $null -eq $data.files) { return $null }
    $map = @{}
    foreach ($entry in @($data.files)) {
        $map[[string]$entry.path] = $entry
    }
    return $map
}

function Test-SafeRelative([string]$relative) {
    if ([string]::IsNullOrWhiteSpace($relative)) { return $false }
    if ($relative.IndexOfAny([char[]]':*?"<>|') -ge 0) { return $false }
    if ($relative.StartsWith('/') -or $relative.StartsWith('\')) { return $false }
    foreach ($segment in ($relative -split '[\\/]')) {
        if ($segment -eq '' -or $segment -eq '.' -or $segment -eq '..' -or $segment.Trim() -ne $segment -or $segment.EndsWith('.')) { return $false }
    }
    return $true
}

function Test-NoReparseBetween([string]$root, [string]$path) {
    # $path itself and every folder up to (excluding) $root must be ordinary.
    $current = $path
    while ($current.Length -gt $root.Length) {
        $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
        if ($item.Attributes -band $ReparsePoint) { return $false }
        $current = [System.IO.Path]::GetDirectoryName($current)
    }
    return $true
}

# ---- validate the call ------------------------------------------------------------------
if (-not [System.IO.Path]::IsPathRooted($InstallDir)) { Stop-Invalid "Programmordner ist kein absoluter Pfad: $InstallDir" }
$root = [System.IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
if ($root.Length -le 3) { Stop-Invalid "Laufwerkswurzel als Programmordner: $root" }
if (-not (Test-Path -LiteralPath $root -PathType Container)) { Stop-Invalid "Programmordner fehlt: $root" }
if ((Get-Item -LiteralPath $root -Force).Attributes -band $ReparsePoint) { Stop-Invalid "Programmordner ist ein Verweis (Junction/Link): $root" }
if (-not $Inventory) { $Inventory = Join-Path $root 'RUNTIME_INVENTORY.json' }
$entries = Read-Inventory $Inventory
if ($null -eq $entries) { Log "Inventar fehlt oder ist unlesbar ($Inventory) – nichts gelöscht."; exit 0 }
$keepSet = @{}
if ($Mode -eq 'Obsolete') {
    $keepEntries = Read-Inventory $Keep
    if ($null -eq $keepEntries) { Log "Neues Inventar fehlt oder ist unlesbar ($Keep) – nichts gelöscht."; exit 0 }
    foreach ($key in $keepEntries.Keys) { $keepSet[($key -replace '/', '\').ToLowerInvariant()] = $true }
}
Log "Bereinigung nach Inventar ($Mode): $root, $($entries.Count) Einträge$(if ($WhatIf) { ' [nur Anzeige]' })"

# ---- files ------------------------------------------------------------------------------
$folders = @{}
foreach ($relativeRaw in $entries.Keys) {
    $entry = $entries[$relativeRaw]
    $relative = ([string]$relativeRaw) -replace '/', '\'
    if ($keepSet.ContainsKey($relative.ToLowerInvariant())) { continue }   # still shipped by the new version
    if (-not (Test-SafeRelative $relative)) { Log "Behalten (ungültiger Pfad im Inventar): $relativeRaw"; $script:kept++; continue }
    $expected = [string]$entry.sha256
    if ($expected -notmatch '^[0-9a-fA-F]{64}$') { Log "Behalten (keine gültige Prüfsumme im Inventar): $relative"; $script:kept++; continue }
    $full = [System.IO.Path]::GetFullPath((Join-Path $root $relative))
    if (-not $full.StartsWith($root + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        Log "Behalten (außerhalb des Programmordners): $relativeRaw"; $script:kept++; continue
    }
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { continue }   # already gone
    try {
        if (-not (Test-NoReparseBetween $root $full)) { Log "Behalten (Verweis/Junction im Pfad): $relative"; $script:kept++; continue }
        if ((Get-Sha256 $full) -ne $expected.ToLowerInvariant()) { Log "Behalten (verändert): $relative"; $script:kept++; continue }
        if (-not $WhatIf) { Remove-Item -LiteralPath $full -Force -ErrorAction Stop }
        Log "Entfernt: $relative"
        $script:removed++
        $folder = [System.IO.Path]::GetDirectoryName($full)
        while ($folder.Length -gt $root.Length) { $folders[$folder] = $true; $folder = [System.IO.Path]::GetDirectoryName($folder) }
    } catch {
        Log "Behalten (Fehler: $($_.Exception.Message)): $relative"; $script:kept++
    }
}

# ---- empty folders, deepest first; never the program folder itself ------------------------
if (-not $WhatIf) {
    foreach ($folder in ($folders.Keys | Sort-Object -Property Length -Descending)) {
        try {
            if (-not (Test-Path -LiteralPath $folder -PathType Container)) { continue }
            if (-not (Test-NoReparseBetween $root $folder)) { continue }
            if (@(Get-ChildItem -LiteralPath $folder -Force).Count -eq 0) {
                Remove-Item -LiteralPath $folder -Force -ErrorAction Stop
            }
        } catch { Log "Ordner bleibt ($($_.Exception.Message)): $folder" }
    }
}
Log "Fertig: $($script:removed) Dateien entfernt, $($script:kept) behalten."
exit 0
