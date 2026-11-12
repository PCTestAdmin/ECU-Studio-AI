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
  -Mode Leftover   (from 1.20.1) the updater's folders next to the program folder,
                   <app>.backup and <app>.update-staging\ECU-Studio-AI, before the program
                   folder (-Reference) is touched. They replace the former blanket
                   [UninstallDelete] rules: a backup can hold the ONLY copy of a program
                   file the user changed, or of an own file whose name a new version took.
                   Removed are only files whose origin is proven:
                     a) listed in the folder's own inventory and unchanged (rules below),
                     b) byte-identical (SHA-256) to the file at the same relative path in
                        the program folder (a copy; the original is handled there),
                     c) unins###.dat in the folder itself whose header is the uninstall log
                        of THIS application (Inno Setup, AppId, AppName), and the matching
                        unins###.exe with this application's version information,
                     d) the folder's RUNTIME_INVENTORY.json, only if it was read as a valid
                        inventory and nothing else is left.
                   Everything else stays and keeps the folder; it is logged. Reparse points
                   inside are neither followed nor removed. Empty ordinary sub-folders are
                   removed (they hold no data); the folder itself only when it is empty.

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
    [ValidateSet('Uninstall', 'Obsolete', 'Leftover')][string]$Mode = 'Uninstall',
    [string]$Inventory = '',
    [string]$Keep = '',
    [string]$Reference = '',
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
# Identity of this application's installer (packaging/installer.iss AppId, AppName, AppPublisher).
$AppId = '{F8CD5330-FC90-4891-BFDA-58E6668C93A5}'
$AppName = 'ECU Studio AI'
$AppPublisher = 'PCTestAdmin'

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

function Test-InnoLog([string]$path) {
    # Inno Setup uninstall log header: ID (64 bytes), AppId (128), AppName (128), zero padded.
    $stream = [System.IO.File]::Open($path, 'Open', 'Read', 'Read')
    try {
        $buffer = New-Object byte[] 320
        if ($stream.Read($buffer, 0, 320) -ne 320) { return $false }
    } finally { $stream.Dispose() }
    $ascii = [System.Text.Encoding]::ASCII
    $id = $ascii.GetString($buffer, 0, 64).TrimEnd([char]0)
    $logAppId = $ascii.GetString($buffer, 64, 128).TrimEnd([char]0)
    $logAppName = $ascii.GetString($buffer, 192, 128).TrimEnd([char]0)
    return ($id -cmatch '^Inno Setup Uninstall Log \([bu]\)( 64-bit)?$') -and $logAppId -ceq $AppId -and $logAppName -ceq $AppName
}

function Test-InnoUninstaller([string]$path) {
    # The uninstaller Inno Setup wrote for THIS application: a PE file with its version information.
    $stream = [System.IO.File]::Open($path, 'Open', 'Read', 'Read')
    try { $magic = $stream.ReadByte() * 256 + $stream.ReadByte() } finally { $stream.Dispose() }
    if ($magic -ne 0x4D5A) { return $false }
    $info = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($path)
    return ([string]$info.FileDescription).Trim() -ceq 'Setup/Uninstall' -and ([string]$info.ProductName).Trim() -ceq $AppName -and
           ([string]$info.CompanyName).Trim() -ceq $AppPublisher
}

function Get-PlainFiles([string]$start) {
    # All files below $start without following or listing reparse points (each one found is logged and counted).
    $files = [System.Collections.Generic.List[string]]::new()
    $pending = [System.Collections.Generic.Stack[string]]::new()
    $pending.Push($start)
    while ($pending.Count -gt 0) {
        foreach ($item in @(Get-ChildItem -LiteralPath $pending.Pop() -Force -ErrorAction Stop)) {
            if ($item.Attributes -band $ReparsePoint) {
                Log "Behalten (Verweis/Junction): $($item.FullName.Substring($start.Length + 1))"
                $script:kept++; $script:reparse++
            } elseif ($item.PSIsContainer) { $pending.Push($item.FullName); $script:plainFolders.Add($item.FullName) }
            else { $files.Add($item.FullName) }
        }
    }
    return , $files
}

# ---- validate the call ------------------------------------------------------------------
if (-not [System.IO.Path]::IsPathRooted($InstallDir)) { Stop-Invalid "Programmordner ist kein absoluter Pfad: $InstallDir" }
$root = [System.IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
if ($root.Length -le 3) { Stop-Invalid "Laufwerkswurzel als Programmordner: $root" }
if (-not (Test-Path -LiteralPath $root -PathType Container)) { Stop-Invalid "Programmordner fehlt: $root" }
if ((Get-Item -LiteralPath $root -Force).Attributes -band $ReparsePoint) { Stop-Invalid "Programmordner ist ein Verweis (Junction/Link): $root" }
$refRoot = ''
if ($Mode -eq 'Leftover') {
    if (-not $Reference -or -not [System.IO.Path]::IsPathRooted($Reference)) { Stop-Invalid "Programmordner (-Reference) fehlt oder ist kein absoluter Pfad: $Reference" }
    $refRoot = [System.IO.Path]::GetFullPath($Reference).TrimEnd('\')
    if ($refRoot.Length -le 3) { Stop-Invalid "Laufwerkswurzel als Programmordner: $refRoot" }
    if (-not (Test-Path -LiteralPath $refRoot -PathType Container)) { Stop-Invalid "Programmordner fehlt: $refRoot" }
    if ((Get-Item -LiteralPath $refRoot -Force).Attributes -band $ReparsePoint) { Stop-Invalid "Programmordner ist ein Verweis (Junction/Link): $refRoot" }
    if ($refRoot -ieq $root -or $root.StartsWith($refRoot + '\', [System.StringComparison]::OrdinalIgnoreCase) -or
        $refRoot.StartsWith($root + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        Stop-Invalid "Ordner und Programmordner überschneiden sich: $root / $refRoot"
    }
}
$script:reparse = 0
$script:plainFolders = [System.Collections.Generic.List[string]]::new()   # Leftover: ordinary sub-folders found
if (-not $Inventory) { $Inventory = Join-Path $root 'RUNTIME_INVENTORY.json' }
$entries = Read-Inventory $Inventory
$inventoryRead = $null -ne $entries
if (-not $inventoryRead) {
    if ($Mode -ne 'Leftover') { Log "Inventar fehlt oder ist unlesbar ($Inventory) – nichts gelöscht."; exit 0 }
    Log "Inventar fehlt oder ist unlesbar ($Inventory) – nur gleiche Kopien und Deinstallerdateien werden entfernt."
    $entries = @{}
}
$keepSet = @{}
if ($Mode -eq 'Obsolete') {
    $keepEntries = Read-Inventory $Keep
    if ($null -eq $keepEntries) { Log "Neues Inventar fehlt oder ist unlesbar ($Keep) – nichts gelöscht."; exit 0 }
    foreach ($key in $keepEntries.Keys) { $keepSet[($key -replace '/', '\').ToLowerInvariant()] = $true }
}
Log "Bereinigung nach Inventar ($Mode): $root, $($entries.Count) Einträge$(if ($WhatIf) { ' [nur Anzeige]' })"

# ---- files ------------------------------------------------------------------------------
$folders = @{}
$gone = @{}             # full paths removed (or, with -WhatIf, that would be removed)
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
        $gone[$full.ToLowerInvariant()] = $true
        $folder = [System.IO.Path]::GetDirectoryName($full)
        while ($folder.Length -gt $root.Length) { $folders[$folder] = $true; $folder = [System.IO.Path]::GetDirectoryName($folder) }
    } catch {
        Log "Behalten (Fehler: $($_.Exception.Message)): $relative"; $script:kept++
    }
}

# ---- Leftover: proven copies and this application's uninstaller files ---------------------
if ($Mode -eq 'Leftover') {
    $inventoryFile = Join-Path $root 'RUNTIME_INVENTORY.json'
    try {
        $rest = @((Get-PlainFiles $root) | Where-Object { -not $gone.ContainsKey($_.ToLowerInvariant()) })
        $innoLogs = @{}
        foreach ($file in $rest) {
            if ([System.IO.Path]::GetDirectoryName($file) -ieq $root -and [System.IO.Path]::GetFileName($file) -match '^unins(\d{3})\.dat$') {
                $number = $Matches[1]
                if (Test-InnoLog $file) { $innoLogs[$number] = $true }
            }
        }
        foreach ($file in $rest) {
            $relative = $file.Substring($root.Length + 1)
            if ($relative -ieq 'RUNTIME_INVENTORY.json') { continue }               # decided below
            try {
                $reason = ''
                $name = [System.IO.Path]::GetFileName($file)
                $atTop = [System.IO.Path]::GetDirectoryName($file) -ieq $root
                $twin = Join-Path $refRoot $relative
                if ((Test-Path -LiteralPath $twin -PathType Leaf) -and (Test-NoReparseBetween $refRoot $twin) -and
                    (Get-Sha256 $twin) -eq (Get-Sha256 $file)) {
                    $reason = 'gleiche Kopie im Programmordner'
                } elseif ($atTop -and $name -match '^unins(\d{3})\.dat$' -and $innoLogs.ContainsKey($Matches[1])) {
                    $reason = 'Deinstallationsprotokoll dieser Anwendung'
                } elseif ($atTop -and $name -match '^unins(\d{3})\.exe$' -and $innoLogs.ContainsKey($Matches[1]) -and (Test-InnoUninstaller $file)) {
                    $reason = 'Deinstallationsprogramm dieser Anwendung'
                }
                if (-not $reason) { Log "Behalten (unbekannt oder verändert, keine gleiche Kopie im Programmordner): $relative"; $script:kept++; continue }
                if (-not $WhatIf) { Remove-Item -LiteralPath $file -Force -ErrorAction Stop }
                Log "Entfernt ($reason): $relative"
                $script:removed++
                $gone[$file.ToLowerInvariant()] = $true
                $folder = [System.IO.Path]::GetDirectoryName($file)
                while ($folder.Length -gt $root.Length) { $folders[$folder] = $true; $folder = [System.IO.Path]::GetDirectoryName($folder) }
            } catch {
                Log "Behalten (Fehler: $($_.Exception.Message)): $relative"; $script:kept++
            }
        }
        # The inventory itself: only if it was valid and is the very last entry (no file, no reparse point left).
        if (Test-Path -LiteralPath $inventoryFile -PathType Leaf) {
            $others = @($rest | Where-Object { -not $gone.ContainsKey($_.ToLowerInvariant()) -and $_ -ine $inventoryFile })
            if ($inventoryRead -and $Inventory -ieq $inventoryFile -and $others.Count -eq 0 -and $script:reparse -eq 0) {
                if (-not $WhatIf) { Remove-Item -LiteralPath $inventoryFile -Force -ErrorAction Stop }
                Log 'Entfernt (Inventar, nichts sonst übrig): RUNTIME_INVENTORY.json'
                $script:removed++
            } else {
                Log 'Behalten (Inventar: andere Dateien bleiben oder Inventar ungültig): RUNTIME_INVENTORY.json'; $script:kept++
            }
        }
        # Sub-folders that are (or become) empty hold no data, e.g. an empty folder the program ships
        # (numpy\random\lib). They are removed below like emptied ones: deepest first, only when empty.
        foreach ($folder in $script:plainFolders) { $folders[$folder] = $true }
    } catch {
        Log "Bereinigung abgebrochen, der Rest bleibt ($($_.Exception.Message))"
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
    # Leftover: the backup/staging folder itself, only when it is completely empty.
    if ($Mode -eq 'Leftover') {
        try {
            if (@(Get-ChildItem -LiteralPath $root -Force).Count -eq 0) { Remove-Item -LiteralPath $root -Force -ErrorAction Stop; Log "Ordner entfernt: $root" }
            else { Log "Ordner bleibt (nicht leer): $root" }
        } catch { Log "Ordner bleibt ($($_.Exception.Message)): $root" }
    }
}
Log "Fertig: $($script:removed) Dateien entfernt, $($script:kept) behalten."
exit 0
