<#
Installer test of a release candidate on a FRESH, isolated Windows runner (never on a developer machine:
it installs, starts, uninstalls and changes per-user settings).

  -Mode Fresh   clean system: install, Start menu and desktop start, icon, version, self-test, GUI smoke,
                end-to-end check with the installed runtime, restart, uninstall, leftovers, reinstall
  -Mode Update  published 1.19.1 installed and used first, then the candidate installed over it; user data,
                settings and another (portable) ECU Studio copy must stay untouched; also the in-app updater path
  -Mode InApp   published old version (default v1.20.0) installed, started from the Start menu and updated FROM ITS
                OWN MENU (UI Automation) with ITS OWN updater (ZIP route); release source = staging server on this
                runner (staging_server.py). Measures what the old uninstaller leaves (A5, known limitation).
  -Mode Repair  old version (v1.20.0) updated by its own updater (ZIP route), then the candidate's setup run over it:
                afterwards the uninstallation must leave nothing but the user's files
  -Mode Chain   v1.19.1 -> candidate (installer) -> next version (-Next) from the candidate's own menu, which uses
                the verified setup.exe (installer route from 1.20.1); obsolete/new files, user files, uninstall
  -Mode Heal    v1.20.0 updated by its own updater (ZIP route) to the candidate, then the candidate's own update to
                -Next (installer route): the leftovers of the old route disappear with the next update
  -Mode Rollback candidate installed; its updater: wrong checksum (refused), failure after the setup (rollback),
                real update to -Next, restore of the previous version, uninstall
  -Mode Blocked v1.20.0 updated by its own updater (ZIP route), candidate's setup run over it (the uninstall log then
                holds the blanket rules of 1.20.0 for <app>.backup and <app>.update-staging). A file held open makes
                the rename of the backup (A) or of the staging folder (B) impossible: the real uninstaller must stop
                before removing anything. Then (C) unlocked: own files stay in the renamed folders.

Every mode also places an unknown file of the user in the program folder: it must survive updates and the
uninstallation (only program files are removed, by inventory + SHA-256 or by the installer's own log).

Writes $Out\results.json; exit code 1 if any check failed.
#>
param(
    [Parameter(Mandatory = $true)][ValidateSet('Fresh', 'Update', 'InApp', 'Repair', 'Chain', 'Heal', 'Rollback', 'Blocked')][string]$Mode,
    [Parameter(Mandatory = $true)][string]$Package,
    [Parameter(Mandatory = $true)][string]$Out,
    [string]$Repository = 'PCTestAdmin/ECU-Studio-AI',
    [string]$OldTag = '',
    [string]$QaPython = '',
    # Second QA package with a higher test version (built from the candidate in the QA workflow only).
    [string]$Next = ''
)
if (-not $OldTag) { $OldTag = @{ Update = 'v1.19.1'; InApp = 'v1.20.0'; Repair = 'v1.20.0'; Chain = 'v1.19.1'; Heal = 'v1.20.0'; Blocked = 'v1.20.0' }[$Mode] }
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory $Out -Force | Out-Null
$qa = $PSScriptRoot
$results = [System.Collections.Generic.List[object]]::new()
$script:failed = $false
function Check([string]$Name, $Ok, $Detail = '') {
    $entry = [ordered]@{ name = $Name; ok = [bool]$Ok; detail = "$Detail" }
    $results.Add($entry)
    Write-Host ("[{0}] {1} {2}" -f ($(if ($Ok) { 'OK' } else { 'FEHLER' }), $Name, $Detail))
    if (-not $Ok) { $script:failed = $true }
}
function Save-Results {
    [ordered]@{ mode = $Mode; runner = "$env:ImageOS $env:ImageVersion"; passed = -not $script:failed; checks = $results } |
        ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 "$Out\results.json"
}

$install = Join-Path $env:LOCALAPPDATA 'Programs\ECU-Studio-AI'
$programs = [Environment]::GetFolderPath('Programs')
$startMenuLink = Join-Path $programs 'ECU Studio AI\ECU Studio AI.lnk'
$desktopLink = Join-Path ([Environment]::GetFolderPath('Desktop')) 'ECU Studio AI.lnk'
$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{F8CD5330-FC90-4891-BFDA-58E6668C93A5}_is1'
$setup = (Get-ChildItem "$Package\ECU-Studio-AI-*-setup.exe" | Select-Object -First 1).FullName
$zip = (Get-ChildItem "$Package\ECU-Studio-AI-*-windows-x64.zip" | Select-Object -First 1).FullName
$version = (Get-Content "$Package\VERSION.txt").Trim()

# The program has to start without any Python of the system: remove every Python from PATH for this script.
$env:PATH = ($env:PATH -split ';' | Where-Object { $_ -and $_ -notmatch '(?i)python|pipx|WindowsApps' }) -join ';'
Remove-Item Env:PYTHONPATH, Env:PYTHONHOME -ErrorAction SilentlyContinue
Check 'kein Python im PATH' (-not (Get-Command python.exe -ErrorAction SilentlyContinue)) ((Get-Command python.exe -ErrorAction SilentlyContinue).Source)

function Get-Snapshot {
    $roots = @((Join-Path $env:LOCALAPPDATA 'Programs'), $programs, [Environment]::GetFolderPath('Desktop'),
               [Environment]::GetFolderPath('CommonDesktopDirectory'))
    $files = foreach ($root in $roots) {
        if (Test-Path $root) { Get-ChildItem $root -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName } }
    }
    $keys = foreach ($hive in 'HKCU:', 'HKLM:') {
        Get-ChildItem "$hive\Software\Microsoft\Windows\CurrentVersion\Uninstall" -ErrorAction SilentlyContinue | ForEach-Object { $_.PSChildName }
    }
    @($files) + @($keys | ForEach-Object { "uninstall:$_" }) | Sort-Object
}
function Get-TreeHash([string]$Root) {
    Get-ChildItem $Root -Recurse -File -Force | ForEach-Object {
        $_.FullName.Substring($Root.Length) + '=' + (Get-FileHash $_.FullName -Algorithm SHA256).Hash } | Sort-Object
}
function Install([string]$Installer, [string]$Log) {
    $p = Start-Process $Installer -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/TASKS="desktopicon"',
        ('/LOG="' + $Log + '"')) -PassThru -Wait
    return $p.ExitCode
}
function Uninstall {
    $p = Start-Process "$install\unins000.exe" -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -PassThru -Wait
    # The uninstaller continues in a temporary copy; wait until it removed the program folder. From 1.20.1 it
    # first checks <app>.backup file by file (SHA-256), which takes longer on a slow runner: up to 4 minutes each.
    for ($i = 0; $i -lt 480 -and (Test-Path "$install\ECU-Studio-AI.exe"); $i++) { Start-Sleep -Milliseconds 500 }
    for ($i = 0; $i -lt 480 -and (Get-Process -Name '_iu*' -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Milliseconds 500 }
    Start-Sleep -Seconds 2
    return $p.ExitCode
}
function Uninstall-Blocked([string]$Log) {
    # An uninstallation that is expected to STOP (the program folder stays): wait for the uninstaller and its
    # temporary copy to end, with a time limit, and return the exit code.
    $p = Start-Process "$install\unins000.exe" -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
        ('/LOG="' + $Log + '"')) -PassThru
    $null = $p.Handle                                   # keeps ExitCode available after the process ended
    if (-not $p.WaitForExit(300000)) {
        Check 'Deinstallation endet innerhalb von 5 Minuten' $false 'Zeitüberschreitung'
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        return 'Zeitüberschreitung'
    }
    for ($i = 0; $i -lt 480 -and (Get-Process -Name '_iu*' -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Milliseconds 500 }
    Start-Sleep -Seconds 2
    return $p.ExitCode
}
function Run-Exe([string[]]$Arguments, [string]$Name) {
    $env:QT_QPA_PLATFORM = 'offscreen'
    $p = Start-Process "$install\ECU-Studio-AI.exe" -ArgumentList $Arguments -PassThru -Wait -WindowStyle Hidden
    Remove-Item Env:QT_QPA_PLATFORM
    return $p.ExitCode
}
function Run-Python([string]$Runtime, [string[]]$Arguments, [bool]$Offscreen = $true) {
    if ($Offscreen) { $env:QT_QPA_PLATFORM = 'offscreen' }
    $p = Start-Process "$Runtime\_internal\python\python.exe" -ArgumentList (@('-I', '-B', ('"' + "$qa\installer_e2e.py" + '"')) + $Arguments) `
        -PassThru -Wait -WindowStyle Hidden -RedirectStandardOutput "$Out\python-$($Arguments[0]).out" -RedirectStandardError "$Out\python-$($Arguments[0]).err"
    Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    return $p.ExitCode
}
function E2E([string]$Runtime, [string]$Step, [string]$Work, [string]$Name, [string[]]$Extra = @(), [bool]$Offscreen = $true) {
    $code = Run-Python $Runtime (@($Step, ('"' + $Work + '"')) + $Extra) $Offscreen
    $report = Join-Path $Work "$Step.json"
    $data = if (Test-Path $report) { Get-Content $report -Raw -Encoding utf8 | ConvertFrom-Json } else { $null }
    foreach ($c in @($data.checks)) { if ($c) { Check "$Name / $($c.name)" $c.ok $c.detail } }
    Check "$Name (Prozess)" ($code -eq 0 -and $data.passed) ("Exit $code " + $(if ($data.error) { $data.error.Split("`n")[-2] }))
}
function Check-Installed([string]$Label, [string]$Expected = $version) {
    Check "$Label`: Programm installiert" (Test-Path "$install\ECU-Studio-AI.exe") $install
    Check "$Label`: Version" ((Get-Content "$install\VERSION.txt").Trim() -eq $Expected) (Get-Content "$install\VERSION.txt")
    $key = Get-ItemProperty $uninstallKey -ErrorAction SilentlyContinue
    Check "$Label`: Eintrag in Apps & Features ($Expected)" ($key -and $key.DisplayVersion -eq $Expected -and
        $key.DisplayName -eq "ECU Studio AI $Expected" -and $key.DisplayIcon -like "*ECU-Studio-AI.exe") `
        "$($key.DisplayName) / $($key.DisplayVersion)"
    $shell = New-Object -ComObject WScript.Shell
    $app = New-Object -ComObject Shell.Application
    foreach ($link in @(@('Startmenü', $startMenuLink), @('Desktop', $desktopLink))) {
        $exists = Test-Path $link[1]
        $target = if ($exists) { $shell.CreateShortcut($link[1]).TargetPath } else { '' }
        $aumid = if ($exists) { $app.Namespace((Split-Path $link[1])).ParseName((Split-Path $link[1] -Leaf)).ExtendedProperty('System.AppUserModel.ID') } else { '' }
        Check "$Label`: Verknüpfung $($link[0])" ($exists -and $target -eq "$install\ECU-Studio-AI.exe" -and $aumid -eq 'PCTestAdmin.ECUStudioAI') "$target / $aumid"
    }
}
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
function Screenshot([string]$Path) {
    try {
        $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        $bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
        [System.Drawing.Graphics]::FromImage($bitmap).CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
        $bitmap.Save($Path)
    } catch { Write-Host "Screenshot nicht möglich: $_" }
}
function Start-FromLink([string]$Label, [string]$Link) {
    # A real start through the shell, as by a click: real desktop, no offscreen platform.
    Start-Process $Link
    $proc = $null
    for ($i = 0; $i -lt 180 -and -not $proc; $i++) {
        Start-Sleep -Milliseconds 500
        $proc = Get-Process pythonw -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -like "$install\*" -and $_.MainWindowTitle -like 'ECU Studio AI*' } | Select-Object -First 1
    }
    Check "Start über $Label" $proc $(if ($proc) { $proc.MainWindowTitle } else { 'kein Hauptfenster' })
    if (-not $proc) { Get-Process pythonw -ErrorAction SilentlyContinue | Stop-Process -Force; return }
    Start-Sleep -Seconds 3
    $safe = $Label -replace '\W', ''
    Screenshot "$Out\start-$safe.png"
    E2E $install 'window' "$Out\window-$safe" "Fenster nach Start über $Label" @("$($proc.Id)") $false
    $null = $proc.CloseMainWindow()
    if (-not $proc.WaitForExit(30000)) { $proc | Stop-Process -Force; Check "$Label`: Programm beendet sich" $false 'erzwungen' }
    else { Check "$Label`: Programm beendet sich normal" $true }
}

# ---- shared helpers for the update/uninstall checks (A5 of 1.20.0) ----------------------------------------
$nextSetup = $null; $nextZip = $null; $nextVersion = $null
if ($Next) {
    $nextSetup = (Get-ChildItem "$Next\ECU-Studio-AI-*-setup.exe" | Select-Object -First 1).FullName
    $nextZip = (Get-ChildItem "$Next\ECU-Studio-AI-*-windows-x64.zip" | Select-Object -First 1).FullName
    $nextVersion = (Get-Content "$Next\VERSION.txt").Trim()
}
$userFileRelative = '_internal\qa-benutzerdatei.txt'
$userFile = Join-Path $install $userFileRelative
$script:userFileHash = $null

function Get-ProgramFiles {
    # Relative paths of all files in the program folder.
    if (-not (Test-Path $install)) { return @() }
    @(Get-ChildItem $install -Recurse -File -Force -ErrorAction SilentlyContinue |
        ForEach-Object { $_.FullName.Substring($install.Length + 1) } | Sort-Object)
}
function Get-InventoryPaths([string]$Path) {
    $data = Get-Content $Path -Raw -Encoding utf8 | ConvertFrom-Json
    @($data.files | ForEach-Object { ([string]$_.path).Replace('/', '\') })
}
function New-UserFile([string]$Label) {
    # An unknown file of the user INSIDE the program folder: no update and no uninstallation may remove it.
    'Notiz des Benutzers im Programmordner (QA)' | Set-Content -Encoding utf8 $userFile
    $script:userFileHash = (Get-FileHash $userFile).Hash
    Check "$Label`: unbekannte Benutzerdatei im Programmordner angelegt" (Test-Path $userFile) $userFileRelative
}
function Check-UserFile([string]$Label) {
    Check "$Label`: unbekannte Benutzerdatei im Programmordner unverändert" (
        (Test-Path $userFile) -and (Get-FileHash $userFile).Hash -eq $script:userFileHash) $userFileRelative
}
function Check-Uninstalled([string]$Label, [string[]]$Expected = @($userFileRelative)) {
    $left = @(Get-ProgramFiles)
    $left | Set-Content -Encoding utf8 ("$Out\leftovers-" + ($Label -replace '\W', '') + '.txt')
    $diff = @($Expected | Where-Object { $left -notcontains $_ } | ForEach-Object { "fehlt $_" }) +
            @($left | Where-Object { $Expected -notcontains $_ } | ForEach-Object { "übrig $_" })
    Check "$Label`: im Programmordner bleibt genau die Benutzerdatei" ($diff.Count -eq 0) (
        "$($left.Count) Dateien übrig; Abweichung: " + (($diff | Select-Object -First 15) -join ', '))
    Check "$Label`: Update-Sicherung entfernt" (-not (Test-Path "$install.backup") -and -not (Test-Path "$install.update-staging") -and
        -not (Test-Path "$install.update-failed"))
    # From 1.20.1 the uninstaller renames both folders to *.erhalten before checking them file by file: with nothing
    # of the user's in them, the renamed folders must be gone as well (removed, not merely renamed).
    Check "$Label`: keine umbenannte Update-Sicherung (*.erhalten) übrig" (
        -not (Test-Path "$install.backup.erhalten*") -and -not (Test-Path "$install.update-staging.erhalten*"))
    $cleanupLog = "$env:LOCALAPPDATA\ECUStudioAI\install-cleanup.log"     # evidence: what the cleanup removed or kept
    if (Test-Path $cleanupLog) { Copy-Item $cleanupLog ("$Out\install-cleanup-" + ($Label -replace '\W', '') + '.log') -Force }
    Check "$Label`: Verknüpfungen entfernt" (-not (Test-Path $startMenuLink) -and -not (Test-Path $desktopLink))
    Check "$Label`: Eintrag in Apps & Features entfernt" (-not (Get-ItemProperty $uninstallKey -ErrorAction SilentlyContinue))
}
function Get-DisplayVersion { [string](Get-ItemProperty $uninstallKey -ErrorAction SilentlyContinue).DisplayVersion }
function Get-Release([string]$Tag, [string[]]$Patterns) {
    # Published files of an older release, verified against their .sha256 assets.
    $dir = Join-Path $Out ('release-' + $Tag)
    $ghArguments = @('release', 'download', $Tag, '--repo', $Repository, '--dir', $dir)
    foreach ($pattern in $Patterns) { $ghArguments += @('--pattern', $pattern) }
    & gh @ghArguments | Out-Host
    foreach ($file in Get-ChildItem "$dir\*.sha256") {
        $expected = ((Get-Content $file.FullName) -split '\s+')[0]
        $target = $file.FullName -replace '\.sha256$', ''
        Check "Download $Tag geprüft: $(Split-Path $target -Leaf)" ((Get-FileHash $target -Algorithm SHA256).Hash.ToLower() -eq $expected)
    }
    return $dir
}
function Get-ZipHashes([string]$Archive) {
    $hashes = @{}
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zipArchive = [System.IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        foreach ($entry in $zipArchive.Entries) {
            if ($entry.Name) {
                $stream = $entry.Open(); $sha = [System.Security.Cryptography.SHA256]::Create()
                $hashes[($entry.FullName -split '/', 2)[1].Replace('/', '\')] = -join ($sha.ComputeHash($stream) | ForEach-Object { $_.ToString('X2') })
                $stream.Dispose()
            }
        }
    } finally { $zipArchive.Dispose() }
    return $hashes
}
function Check-PackageInstalled([string]$Label, [string]$Archive) {
    # Every file of the package installed byte for byte; nothing else except the uninstaller and the user's file.
    $hashes = Get-ZipHashes $Archive
    $wrong = @($hashes.Keys | Where-Object { -not (Test-Path "$install\$_") -or (Get-FileHash "$install\$_").Hash -ne $hashes[$_] })
    Check "$Label`: alle Dateien des Pakets installiert (SHA-256)" ($wrong.Count -eq 0) "$($hashes.Count) Dateien, abweichend: $($wrong -join ', ')"
    $extra = @(Get-ProgramFiles | Where-Object { -not $hashes.ContainsKey($_) -and $_ -notmatch '^unins000\.(exe|dat)$' -and $_ -ne $userFileRelative })
    Check "$Label`: keine Dateien außer Paket, Deinstallationsprogramm und Benutzerdatei" ($extra.Count -eq 0) "$($extra.Count): $($extra -join ', ')"
}
function Invoke-Updater([string[]]$Arguments, [string]$Log) {
    # As the application does it (ui/updates.py launch_pending): a copy of the INSTALLED updater runs from outside
    # the program folder after the program has ended.
    $work = Join-Path $Out ('updater-' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
    New-Item -ItemType Directory $work -Force | Out-Null
    Copy-Item "$install\_internal\updater.ps1" "$work\updater.ps1"
    $env:ECU_UPDATER_QUIET = '1'
    $env:QT_QPA_PLATFORM = 'offscreen'
    powershell -NoProfile -ExecutionPolicy Bypass -File "$work\updater.ps1" -InstallDir $install @Arguments -LogFile $Log | Out-Host
    $code = $LASTEXITCODE
    Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    return $code
}
function Count-Requests([string]$Like) {
    @($script:inappRequests | Where-Object { $_.status -eq 200 -and $_.path -like $Like }).Count
}
function Invoke-InAppUpdate([string]$Source, [string]$From, [string]$To, [string]$Label) {
    # Real in-app update: the installed version is started from the Start menu and updated FROM ITS OWN MENU
    # (UI Automation). Release source = STAGING server on this runner (staging_server.py); no tag, no release.
    if (-not $QaPython) { throw '-QaPython fehlt' }
    $staging = Join-Path $Out "staging-$Label"
    $uiOut = Join-Path $Out "inapp-$Label"
    $hosts = "$env:SystemRoot\System32\drivers\etc\hosts"
    $hostsBefore = Get-Content $hosts -Raw
    $updateLog = "$env:LOCALAPPDATA\ECUStudioAI\updates\update.log"
    $setupLog = [System.IO.Path]::ChangeExtension($updateLog, '.setup.log')
    Remove-Item $updateLog, $setupLog -ErrorAction SilentlyContinue
    $server = $null; $caThumb = $null
    $script:inappRequests = @(); $script:inappLog = ''; $script:inappNew = $false
    try {
        $server = Start-Process $QaPython -ArgumentList @('-I', ('"' + "$qa\staging_server.py" + '"'), ('"' + $staging + '"'),
            ('"' + $Source + '"'), $Repository) -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput "$Out\staging-$Label.out" -RedirectStandardError "$Out\staging-$Label.err"
        for ($i = 0; $i -lt 60 -and -not (Test-Path "$staging\ready"); $i++) { Start-Sleep -Milliseconds 500 }
        Check "$Label`: Staging-Quelle läuft (nur auf diesem Runner)" (Test-Path "$staging\ready") (Get-Content "$Out\staging-$Label.err" -Raw -ErrorAction SilentlyContinue)
        $caThumb = (Import-Certificate "$staging\ca.cer" -CertStoreLocation Cert:\LocalMachine\Root).Thumbprint
        Add-Content $hosts "`r`n127.0.0.1 api.github.com`r`n127.0.0.1 github.com"
        ipconfig /flushdns | Out-Null
        # Probe with the update code of the INSTALLED version (its runtime, Windows trust store).
        $probe = & "$install\_internal\python\python.exe" -I -B -c "from ecu_studio.core import updates; r = updates.fetch_latest(); print(r.version if r else 'none', updates.update_available('$From', r))" 2>&1
        Check "$Label`: installierte Version $From sieht $To als neueste stabile Version" ("$probe".Trim() -eq "$To True") "$probe"

        Start-Process $startMenuLink
        $proc = $null
        for ($i = 0; $i -lt 180 -and -not $proc; $i++) {
            Start-Sleep -Milliseconds 500
            $proc = Get-Process pythonw -ErrorAction SilentlyContinue |
                Where-Object { $_.Path -like "$install\*" -and $_.MainWindowTitle -like "*v$From*" } | Select-Object -First 1
        }
        Check "$Label`: $From über das Startmenü gestartet" $proc $(if ($proc) { $proc.MainWindowTitle } else { 'kein Hauptfenster' })
        Start-Sleep -Seconds 3
        $p = Start-Process $QaPython -ArgumentList @('-I', ('"' + "$qa\inapp_ui.py" + '"'), "$($proc.Id)", ('"' + $uiOut + '"'),
            $From, $To) -PassThru -Wait -WindowStyle Hidden -RedirectStandardOutput "$Out\inapp-ui-$Label.out" -RedirectStandardError "$Out\inapp-ui-$Label.err"
        $ui = if (Test-Path "$uiOut\inapp-ui.json") { Get-Content "$uiOut\inapp-ui.json" -Raw -Encoding utf8 | ConvertFrom-Json }
        foreach ($c in @($ui.checks)) { if ($c) { Check "$Label / In-App-Update (Bedienung) / $($c.name)" $c.ok $c.detail } }
        Check "$Label`: In-App-Update (Bedienung, Prozess)" ($p.ExitCode -eq 0 -and $ui.passed) ("Exit $($p.ExitCode) " + $(if ($ui.error) { $ui.error.Split("`n")[-2] }))

        # The updater (started by the running version) waits for it to end, installs, self-checks and restarts.
        $new = $null
        for ($i = 0; $i -lt 900 -and -not $new; $i++) {
            Start-Sleep -Milliseconds 500
            $new = Get-Process pythonw -ErrorAction SilentlyContinue |
                Where-Object { $_.Path -like "$install\*" -and $_.MainWindowTitle -like "*v$To*" } | Select-Object -First 1
        }
        $script:inappLog = [string](Get-Content $updateLog -Raw -Encoding utf8 -ErrorAction SilentlyContinue)
        Copy-Item $updateLog "$Out\update-$Label.log" -ErrorAction SilentlyContinue
        Copy-Item $setupLog "$Out\update-$Label.setup.log" -ErrorAction SilentlyContinue
        Check "$Label`: Updater: installiert, Selbsttest, Neustart" ($script:inappLog -match 'Update (per Installer )?installiert') (
            ($script:inappLog -split "`n" | Select-Object -Last 3) -join ' | ')
        Check "$Label`: Neustart als $To (Fenstertitel)" $new $(if ($new) { $new.MainWindowTitle } else { 'kein Fenster' })
        if ($new) {
            $script:inappNew = $true
            Start-Sleep -Seconds 5          # the new version adjusts "Apps & Features" at start
            Screenshot "$Out\inapp-$Label-neue-version.png"
            E2E $install 'window' "$Out\window-$Label" "$Label`: Fenster nach In-App-Update" @("$($new.Id)") $false
            $null = $new.CloseMainWindow()
            Check "$Label`: neue Version beendet sich normal" ($new.WaitForExit(30000))
        }
        $script:inappRequests = @(Get-Content "$staging\requests.log" -ErrorAction SilentlyContinue | ForEach-Object { $_ | ConvertFrom-Json })
        Check "$Label`: Anfragen an die Staging-Quelle (Information)" $true (($script:inappRequests | ForEach-Object { "$($_.status) $($_.path)" }) -join '; ')
    } catch {
        Check "$Label`: In-App-Ablauf ohne Ausnahme" $false $_.Exception.Message
    } finally {
        Set-Content $hosts $hostsBefore -NoNewline
        ipconfig /flushdns | Out-Null
        if ($caThumb) { Remove-Item "Cert:\LocalMachine\Root\$caThumb" -ErrorAction SilentlyContinue }
        if ($server) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
        Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$install*" } | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    Check "$Label`: Staging entfernt (hosts wiederhergestellt, Test-CA gelöscht)" ((Get-Content $hosts -Raw) -eq $hostsBefore -and
        -not ($caThumb -and (Test-Path "Cert:\LocalMachine\Root\$caThumb")))
}
function Check-Running([string]$Label) {
    Check "$Label`: Selbsttest" ((Run-Exe @('--self-check')) -eq 0)
    $safe = $Label -replace '\W', ''
    $code = Run-Exe @('--smoke-test', ('"' + "$Out\gui-smoke-$safe" + '"'))
    $smoke = if (Test-Path "$Out\gui-smoke-$safe\gui-smoke.json") { Get-Content "$Out\gui-smoke-$safe\gui-smoke.json" -Raw -Encoding utf8 | ConvertFrom-Json }
    Check "$Label`: GUI-Smoke-Test inkl. Checksummen" ($code -eq 0 -and $smoke.passed -and $smoke.checksums) "Exit $code"
}

if ($Mode -eq 'Fresh') {
    $portable = 'C:\QA\other-ecu-studio'
    Expand-Archive $zip $portable -Force
    $portableBefore = Get-TreeHash $portable
    Check 'sauberes System: keine ECU-Studio-Installation' (-not (Test-Path $install) -and -not (Get-ItemProperty $uninstallKey -ErrorAction SilentlyContinue)) $install
    Check 'sauberes System: keine Benutzerdaten' (-not (Test-Path "$HOME\.ecu_studio_ai") -and -not (Test-Path 'HKCU:\Software\ECU Studio'))
    $before = Get-Snapshot

    Check '1. Installation' ((Install $setup "$Out\install-1.log") -eq 0) $setup
    Check-Installed 'Installation'
    Check 'EXE-Selbsttest (--self-check)' ((Run-Exe @('--self-check')) -eq 0)
    $code = Run-Exe @('--smoke-test', ('"' + "$Out\gui-smoke" + '"'))
    $smoke = if (Test-Path "$Out\gui-smoke\gui-smoke.json") { Get-Content "$Out\gui-smoke\gui-smoke.json" -Raw -Encoding utf8 | ConvertFrom-Json }
    Check 'GUI-Smoke-Test der installierten EXE' ($code -eq 0 -and $smoke.passed -and $smoke.checksums) "Exit $code, $(@($smoke.checks).Count) Prüfungen"

    Start-FromLink 'Startmenü' $startMenuLink
    Start-FromLink 'Desktopverknüpfung' $desktopLink

    E2E $install 'first' "$Out\e2e" 'Ablauf'
    E2E $install 'restart' "$Out\e2e" 'Neustart'

    Check '2. Deinstallation' ((Uninstall) -eq 0)
    Check 'Programmordner entfernt' (-not (Test-Path $install)) ((Get-ChildItem $install -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object FullName) -join ', ')
    Check 'Verknüpfungen entfernt' (-not (Test-Path $startMenuLink) -and -not (Test-Path $desktopLink))
    Check 'Eintrag in Apps & Features entfernt' (-not (Get-ItemProperty $uninstallKey -ErrorAction SilentlyContinue))
    $after = Get-Snapshot
    $diff = Compare-Object $before $after | ForEach-Object { "$($_.SideIndicator) $($_.InputObject)" }
    Check 'keine unerwarteten Dateien oder Einträge zurück' (-not $diff) ($diff -join '; ')
    Check 'Benutzerdaten bleiben nach Deinstallation (gewollt, dokumentiert)' ((Test-Path "$HOME\.ecu_studio_ai") -and (Test-Path 'HKCU:\Software\ECU Studio')) `
        ((Get-ChildItem "$HOME\.ecu_studio_ai" -Force -ErrorAction SilentlyContinue | ForEach-Object Name) -join ', ')
    Check 'Projekt und korrigierte Kopie des Benutzers bleiben' ((Test-Path "$Out\e2e\qa-projekt.ecustudio") -and (Test-Path "$Out\e2e\testfirmware_pruefsumme.bin.korrektur.json"))

    Check '3. erneute Installation' ((Install $setup "$Out\install-2.log") -eq 0)
    Check-Installed 'Neuinstallation'
    Check 'EXE-Selbsttest nach Neuinstallation' ((Run-Exe @('--self-check')) -eq 0)
    E2E $install 'restart' "$Out\e2e" 'Neuinstallation öffnet Projekt und Einstellungen'
    New-UserFile 'Neuinstallation'
    Check '4. Deinstallation' ((Uninstall) -eq 0)
    Check-Uninstalled 'Deinstallation mit Benutzerdatei im Programmordner'
    Check-UserFile 'nach Deinstallation'
    Remove-Item $install -Recurse -Force -ErrorAction SilentlyContinue   # test cleanup: the user's own file, removed by the test, not the uninstaller
    $diff = Compare-Object $before (Get-Snapshot) | ForEach-Object { "$($_.SideIndicator) $($_.InputObject)" }
    Check 'nach zweiter Deinstallation nichts zurück (außer der entfernten Benutzerdatei)' (-not $diff) ($diff -join '; ')
    $portableAfter = Get-TreeHash $portable
    Check 'andere ECU-Studio-Kopie unverändert' (-not (Compare-Object $portableBefore $portableAfter)) "$($portableBefore.Count) Dateien"
}

if ($Mode -eq 'Update') {
    $old = Join-Path $Out 'old'
    gh release download $OldTag --repo $Repository --pattern '*-setup.exe*' --pattern '*-windows-x64.zip*' --dir $old
    foreach ($file in Get-ChildItem "$old\*.sha256") {
        $expected = ((Get-Content $file.FullName) -split '\s+')[0]
        $target = $file.FullName -replace '\.sha256$', ''
        Check "Download $OldTag geprüft: $(Split-Path $target -Leaf)" ((Get-FileHash $target -Algorithm SHA256).Hash.ToLower() -eq $expected)
    }
    $oldSetup = (Get-ChildItem "$old\*-setup.exe").FullName
    $oldZip = (Get-ChildItem "$old\*-windows-x64.zip").FullName
    $portable = 'C:\QA\other-ecu-studio-1.19.1'
    Expand-Archive $oldZip $portable -Force
    $portableBefore = Get-TreeHash $portable

    Check "Installation $OldTag" ((Install $oldSetup "$Out\install-old.log") -eq 0)
    Check "$OldTag installiert" ((Get-Content "$install\VERSION.txt").Trim() -eq $OldTag.TrimStart('v'))
    Check "$OldTag Selbsttest" ((Run-Exe @('--self-check')) -eq 0)
    E2E $install 'seed' "$Out\user" "Benutzerdaten mit $OldTag angelegt"
    New-Item -ItemType Directory "$HOME\.ecu_studio_ai" -Force | Out-Null
    'private Notiz des Benutzers' | Set-Content -Encoding utf8 "$HOME\.ecu_studio_ai\qa-private-note.txt"
    $userFiles = @("$Out\user\alt.ecustudio", "$Out\user\alt.bin")
    $userBefore = $userFiles | ForEach-Object { (Get-FileHash $_).Hash }
    $noteBefore = (Get-FileHash "$HOME\.ecu_studio_ai\qa-private-note.txt").Hash
    $oldFiles = Get-TreeHash $install
    New-UserFile "Update ($OldTag)"

    Check 'Update: Kandidat über 1.19.1 installiert' ((Install $setup "$Out\install-update.log") -eq 0)
    Check-Installed 'Update'
    $zipFiles = @{}
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($zip)
    foreach ($entry in $archive.Entries) {
        if ($entry.Name) {
            $stream = $entry.Open(); $sha = [System.Security.Cryptography.SHA256]::Create()
            $zipFiles[($entry.FullName -split '/', 2)[1].Replace('/', '\')] = -join ($sha.ComputeHash($stream) | ForEach-Object { $_.ToString('X2') })
            $stream.Dispose()
        }
    }
    $archive.Dispose()
    $wrong = @($zipFiles.Keys | Where-Object { -not (Test-Path "$install\$_") -or (Get-FileHash "$install\$_").Hash -ne $zipFiles[$_] })
    Check 'Update: alle Dateien des Kandidaten installiert (SHA-256)' ($wrong.Count -eq 0) "$($zipFiles.Count) Dateien, abweichend: $($wrong -join ', ')"
    Check 'Update: Checksummensystem vorhanden' (Test-Path "$install\_internal\app\ecu_studio\core\integrity.py")
    $leftover = @(Get-ProgramFiles | Where-Object { -not $zipFiles.ContainsKey($_) -and $_ -notmatch '^unins000\.(exe|dat)$' -and $_ -ne $userFileRelative })
    Check 'Update: keine unveränderten Dateien der alten Version übrig (nach Inventar entfernt)' ($leftover.Count -eq 0) "$($leftover.Count): $($leftover -join ', ')"
    Check-UserFile 'Update'
    Check 'Update: Selbsttest' ((Run-Exe @('--self-check')) -eq 0)
    $code = Run-Exe @('--smoke-test', ('"' + "$Out\gui-smoke-update" + '"'))
    $smoke = if (Test-Path "$Out\gui-smoke-update\gui-smoke.json") { Get-Content "$Out\gui-smoke-update\gui-smoke.json" -Raw -Encoding utf8 | ConvertFrom-Json }
    Check 'Update: GUI-Smoke-Test inkl. Checksummen' ($code -eq 0 -and $smoke.passed -and $smoke.checksums) "Exit $code"
    E2E $install 'compat' "$Out\user" 'Update: Projekt und Einstellungen aus 1.19.1'
    E2E $install 'first' "$Out\e2e" 'Update: Ablauf'
    Check 'Update: Projekt und BIN des Benutzers unverändert' (-not (Compare-Object $userBefore ($userFiles | ForEach-Object { (Get-FileHash $_).Hash })))
    Check 'Update: private Datei in .ecu_studio_ai unverändert' ((Get-FileHash "$HOME\.ecu_studio_ai\qa-private-note.txt").Hash -eq $noteBefore)

    Check 'Deinstallation nach Update' ((Uninstall) -eq 0)
    Check-Uninstalled 'Deinstallation nach Update'
    Check-UserFile 'Deinstallation nach Update'
    Check 'Benutzerdaten nach Deinstallation erhalten' ((Get-FileHash "$HOME\.ecu_studio_ai\qa-private-note.txt").Hash -eq $noteBefore -and (Test-Path "$Out\user\alt.ecustudio"))

    # In-app update path: the updater of the old portable package replaces it with the candidate's ZIP.
    $work = Join-Path $Out 'inapp'
    Expand-Archive $oldZip $work -Force
    $inapp = Join-Path $work 'ECU-Studio-AI'
    Copy-Item "$inapp\_internal\updater.ps1" "$work\updater.ps1"
    $sha = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
    $env:ECU_UPDATER_QUIET = '1'
    $env:QT_QPA_PLATFORM = 'offscreen'
    powershell -NoProfile -ExecutionPolicy Bypass -File "$work\updater.ps1" -InstallDir $inapp -Archive $zip -Sha256 $sha -LogFile "$work\update.log"
    $code = $LASTEXITCODE
    Remove-Item Env:QT_QPA_PLATFORM
    Check 'In-App-Updater 1.19.1 -> Kandidat' ($code -eq 0 -and (Test-Path "$inapp\_internal\app\ecu_studio\core\integrity.py")) "Exit $code"
    $portableAfter = Get-TreeHash $portable
    Check 'andere ECU-Studio-Kopie (portable 1.19.1) unverändert' (-not (Compare-Object $portableBefore $portableAfter)) "$($portableBefore.Count) Dateien"
}

if ($Mode -eq 'InApp') {
    # The path of existing installations: the published old version updates itself with ITS OWN updater (ZIP route,
    # cannot be changed afterwards). The candidate adjusts "Apps & Features" at its first start. The old
    # uninstaller only knows the files of its own installer run: what it leaves is measured exactly here.
    $old = Get-Release $OldTag @('*-setup.exe*')
    $oldVersion = $OldTag.TrimStart('v')
    Check "Installation $OldTag" ((Install (Get-ChildItem "$old\*-setup.exe").FullName "$Out\install-old.log") -eq 0)
    Check "$OldTag installiert" ((Get-Content "$install\VERSION.txt").Trim() -eq $oldVersion)
    E2E $install 'seed' "$Out\user" "Benutzerdaten mit $OldTag angelegt"
    New-Item -ItemType Directory "$HOME\.ecu_studio_ai" -Force | Out-Null
    'private Notiz des Benutzers' | Set-Content -Encoding utf8 "$HOME\.ecu_studio_ai\qa-private-note.txt"
    $userFiles = @("$Out\user\alt.ecustudio", "$Out\user\alt.bin")
    $userBefore = $userFiles | ForEach-Object { (Get-FileHash $_).Hash }
    $noteBefore = (Get-FileHash "$HOME\.ecu_studio_ai\qa-private-note.txt").Hash
    New-UserFile "vor In-App-Update ($OldTag)"
    $oldTree = Get-TreeHash $install

    Invoke-InAppUpdate ([string](Resolve-Path $Package)) $oldVersion $version 'alt'
    Check 'Programm hat Release-Info, ZIP-Prüfsumme und ZIP geladen (Weg des alten Updaters)' (
        (Count-Requests '*/releases/latest') -ge 1 -and (Count-Requests '*.zip.sha256') -ge 1 -and (Count-Requests '*.zip') -ge 1)

    Check 'nach In-App-Update: Version' ((Get-Content "$install\VERSION.txt").Trim() -eq $version) (Get-Content "$install\VERSION.txt")
    Check-PackageInstalled 'nach In-App-Update' $zip
    Check 'nach In-App-Update: Sicherung der alten Version vorhanden' ((Get-Content "$install.backup\VERSION.txt" -ErrorAction SilentlyContinue) -eq $oldVersion -and
        -not (Compare-Object $oldTree (Get-TreeHash "$install.backup")))
    Check 'nach In-App-Update: Deinstallationsprogramm erhalten' ((Test-Path "$install\unins000.exe") -and (Test-Path "$install\unins000.dat"))
    Check-Installed 'nach In-App-Update und Start der neuen Version (Apps & Features)'
    Check-Running 'nach In-App-Update'
    E2E $install 'compat' "$Out\user" "nach In-App-Update: Projekt und Einstellungen aus $OldTag"
    Check 'nach In-App-Update: Projekt und BIN des Benutzers unverändert' (-not (Compare-Object $userBefore ($userFiles | ForEach-Object { (Get-FileHash $_).Hash })))
    Check 'nach In-App-Update: private Datei in .ecu_studio_ai unverändert' ((Get-FileHash "$HOME\.ecu_studio_ai\qa-private-note.txt").Hash -eq $noteBefore)
    Check-UserFile 'nach In-App-Update'

    # Files the candidate ships and the old version did not: the old uninstaller does not know them.
    $oldInventory = Get-InventoryPaths "$install.backup\RUNTIME_INVENTORY.json"
    $newOnly = @(Get-InventoryPaths "$install\RUNTIME_INVENTORY.json" | Where-Object { $oldInventory -notcontains $_ })
    $newOnly | Set-Content -Encoding utf8 "$Out\new-files-vs-$OldTag.txt"
    Check "Information: Dateien, die erst der Kandidat mitbringt (gegenüber $OldTag)" $true "$($newOnly.Count): $($newOnly -join ', ')"
    Check "Deinstallation mit dem Deinstallationsprogramm von $OldTag" ((Uninstall) -eq 0)
    $left = @(Get-ProgramFiles)
    $left | Set-Content -Encoding utf8 "$Out\leftovers-after-uninstall.txt"
    $unexpected = @($left | Where-Object { $_ -ne $userFileRelative -and $newOnly -notcontains $_ })
    Check "Deinstallation durch $OldTag`: Reste nur aus neuen Dateien des Kandidaten (bekannte Einschränkung alter Installationen, A5)" (
        $unexpected.Count -eq 0) ("$($left.Count) Dateien übrig, unerwartet: " + ($unexpected -join ', '))
    Check "Information: Restdateien nach Deinstallation durch $OldTag" $true ("$($left.Count): " + ($left -join ', '))
    Check-UserFile "nach Deinstallation durch $OldTag"
    Check 'Update-Sicherung entfernt' (-not (Test-Path "$install.backup"))
    Check 'Eintrag in Apps & Features entfernt' (-not (Get-ItemProperty $uninstallKey -ErrorAction SilentlyContinue))
    Check 'Benutzerdaten nach Deinstallation erhalten' ((Get-FileHash "$HOME\.ecu_studio_ai\qa-private-note.txt").Hash -eq $noteBefore)

    # Remedy from the release notes for users who ALREADY uninstalled with the old uninstaller: run the candidate's
    # setup once more and uninstall again. Nothing but the user's file may remain (the leftovers are inventory files).
    Check 'Nachträgliche Reparatur: Setup des Kandidaten über die Restdateien' ((Install $setup "$Out\install-after-old-uninstall.log") -eq 0)
    Check-Installed 'Nachträgliche Reparatur'
    Check-UserFile 'Nachträgliche Reparatur'
    Check 'Nachträgliche Reparatur: Deinstallation' ((Uninstall) -eq 0)
    Check-Uninstalled 'Nachträgliche Reparatur'
    Check-UserFile 'Nachträgliche Reparatur, nach Deinstallation'
    Check 'Nachträgliche Reparatur: Benutzerdaten erhalten' ((Get-FileHash "$HOME\.ecu_studio_ai\qa-private-note.txt").Hash -eq $noteBefore)
}

if ($Mode -eq 'Repair') {
    # Remedy for installations that an old updater (1.20.0 and older) updated: run the setup of the new version once.
    $old = Get-Release $OldTag @('*-setup.exe*')
    $oldVersion = $OldTag.TrimStart('v')
    Check "Installation $OldTag" ((Install (Get-ChildItem "$old\*-setup.exe").FullName "$Out\install-old.log") -eq 0)
    New-UserFile "Reparatur ($OldTag)"
    $sha = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
    $code = Invoke-Updater @('-Archive', $zip, '-Sha256', $sha) "$Out\update-old-updater.log"
    Check "ZIP-Update mit dem Updater von $OldTag" ($code -eq 0 -and (Get-Content "$install\VERSION.txt").Trim() -eq $version) "Exit $code"
    Check "Information: Apps & Features nach dem alten Updater (vor dem ersten Start)" $true (Get-DisplayVersion)
    Check-UserFile 'nach ZIP-Update'
    Check 'Reparatur: Setup des Kandidaten über die aktualisierte Installation' ((Install $setup "$Out\install-repair.log") -eq 0)
    Check-Installed 'Reparatur'
    Check-PackageInstalled 'Reparatur' $zip
    Check-UserFile 'Reparatur'
    Check-Running 'Reparatur'
    Check 'Reparatur: Update-Sicherung des alten Updaters vor der Deinstallation vorhanden' (Test-Path "$install.backup\VERSION.txt")
    # The backup can hold the ONLY copy of a user's file or of a program file the user changed. From 1.20.1 there is
    # no blanket [UninstallDelete] rule, and the old rules of 1.20.0 that remain in unins000.dat must not reach the
    # folder either: the real uninstaller must keep exactly these files (and their inventory) in <app>.backup.erhalten.
    $relOwn = '_internal\qa-nur-in-der-sicherung.txt'; $relChanged = '_internal\app\ecu_studio\main.py'
    'nur in der Sicherung' | Set-Content -Encoding utf8 "$install.backup\$relOwn"
    Add-Content -Encoding utf8 "$install.backup\$relChanged" '# vom Benutzer geaendert, nur in der Sicherung'
    $keptBefore = @($relOwn, $relChanged) | ForEach-Object { (Get-FileHash "$install.backup\$_").Hash }
    Check 'Deinstallation nach Reparatur' ((Uninstall) -eq 0)
    $kept = "$install.backup.erhalten"
    $keptAfter = @($relOwn, $relChanged) | ForEach-Object { if (Test-Path "$kept\$_") { (Get-FileHash "$kept\$_").Hash } else { 'fehlt' } }
    Check 'Deinstallation nach Reparatur: eigene und veränderte Datei der Update-Sicherung unverändert erhalten' (
        -not (Compare-Object $keptBefore $keptAfter)) ($keptAfter -join ', ')
    $backupLeft = @(Get-ChildItem $kept -Recurse -File -Force -ErrorAction SilentlyContinue |
        ForEach-Object { $_.FullName.Substring($kept.Length + 1) })
    Check 'Deinstallation nach Reparatur: in ECU-Studio-AI.backup.erhalten bleiben genau diese zwei Dateien und ihr Inventar' (
        $backupLeft.Count -eq 3 -and -not (Compare-Object $backupLeft @('RUNTIME_INVENTORY.json', $relChanged, $relOwn))) (
        "$($backupLeft.Count): " + (($backupLeft | Select-Object -First 15) -join ', '))
    # Disposable runner only: the test removes what the uninstaller rightly kept, then checks everything else.
    if (Test-Path -LiteralPath $kept) { Remove-Item -LiteralPath $kept -Recurse -Force }
    Check-Uninstalled 'Deinstallation nach Reparatur'
    Check-UserFile 'Deinstallation nach Reparatur'
}

if ($Mode -eq 'Chain') {
    # Several versions in a row: old release -> candidate (installer) -> next version from the candidate's menu.
    if (-not $Next) { throw '-Next fehlt' }
    $old = Get-Release $OldTag @('*-setup.exe*')
    $oldVersion = $OldTag.TrimStart('v')
    Check "Installation $OldTag" ((Install (Get-ChildItem "$old\*-setup.exe").FullName "$Out\install-old.log") -eq 0)
    E2E $install 'seed' "$Out\user" "Benutzerdaten mit $OldTag angelegt"
    New-Item -ItemType Directory "$HOME\.ecu_studio_ai" -Force | Out-Null
    'private Notiz des Benutzers' | Set-Content -Encoding utf8 "$HOME\.ecu_studio_ai\qa-private-note.txt"
    $noteBefore = (Get-FileHash "$HOME\.ecu_studio_ai\qa-private-note.txt").Hash
    $userFiles = @("$Out\user\alt.ecustudio", "$Out\user\alt.bin")
    $userBefore = $userFiles | ForEach-Object { (Get-FileHash $_).Hash }
    New-UserFile "Kette ($OldTag)"

    Check "Kette 1: Kandidat $version per Installer über $OldTag" ((Install $setup "$Out\install-candidate.log") -eq 0)
    Check-Installed 'Kette 1'
    Check-PackageInstalled 'Kette 1' $zip
    Check-UserFile 'Kette 1'
    $candidateTree = Get-TreeHash $install

    $route = & "$install\_internal\python\python.exe" -I -B -c "from pathlib import Path; from ecu_studio.core import updates; print(updates.installer_registration(Path(r'$install')) is not None)" 2>&1
    Check 'Kette 2: Kandidat erkennt seine Installer-Installation' ("$route".Trim() -eq 'True') "$route"
    Invoke-InAppUpdate ([string](Resolve-Path $Next)) $version $nextVersion 'kette'
    Check 'Kette 2: Update über den geprüften Installer, nicht über das ZIP' (
        (Count-Requests '*-setup.exe.sha256') -ge 1 -and (Count-Requests '*-setup.exe') -ge 1 -and (Count-Requests '*.zip') -eq 0)
    Check 'Kette 2: Updater meldet Installer-Weg' ($script:inappLog -match 'Update per Installer installiert') ''
    Check-Installed 'Kette 2' $nextVersion
    Check-PackageInstalled 'Kette 2' $nextZip
    Check 'Kette 2: Datei, die die neue Version nicht mehr enthält, entfernt' (-not (Test-Path "$install\_internal\app\ecu_studio\qa_dropped_in_next.py"))
    Check 'Kette 2: neue Datei der neuen Version vorhanden' (Test-Path "$install\_internal\app\ecu_studio\qa_next_only.py")
    Check 'Kette 2: Sicherung = Kandidat vor dem Update (SHA-256 aller Dateien)' (-not (Compare-Object $candidateTree (Get-TreeHash "$install.backup")))
    Check-UserFile 'Kette 2'
    Check-Running 'Kette 2'
    E2E $install 'compat' "$Out\user" "Kette 2: Projekt und Einstellungen aus $OldTag"
    Check 'Kette 2: Projekt und BIN des Benutzers unverändert' (-not (Compare-Object $userBefore ($userFiles | ForEach-Object { (Get-FileHash $_).Hash })))

    Check 'Kette 3: Deinstallation' ((Uninstall) -eq 0)
    Check-Uninstalled 'Kette 3'
    Check-UserFile 'Kette 3'
    Check 'Kette 3: Benutzerdaten erhalten' ((Get-FileHash "$HOME\.ecu_studio_ai\qa-private-note.txt").Hash -eq $noteBefore)
}

if ($Mode -eq 'Heal') {
    # Realistic path of an existing installation: 1.20.0 updates itself with ITS OWN updater (ZIP route) to the
    # candidate; the next update is done by the candidate's updater over the verified setup (installer route).
    if (-not $Next) { throw '-Next fehlt' }
    $old = Get-Release $OldTag @('*-setup.exe*')
    Check "Installation $OldTag" ((Install (Get-ChildItem "$old\*-setup.exe").FullName "$Out\install-old.log") -eq 0)
    New-UserFile "Heilung ($OldTag)"
    $sha = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
    $code = Invoke-Updater @('-Archive', $zip, '-Sha256', $sha) "$Out\heal-1.log"
    Check "Heilung 1: ZIP-Update mit dem Updater von $OldTag" ($code -eq 0 -and (Get-Content "$install\VERSION.txt").Trim() -eq $version) "Exit $code"
    $nextSha = (Get-FileHash $nextSetup -Algorithm SHA256).Hash.ToLower()
    $code = Invoke-Updater @('-Installer', $nextSetup, '-Sha256', $nextSha, '-ExpectedVersion', $nextVersion) "$Out\heal-2.log"
    Check "Heilung 2: Update des Kandidaten auf $nextVersion per Installer" ($code -eq 0) "Exit $code"
    Check-Installed 'Heilung 2' $nextVersion
    Check-PackageInstalled 'Heilung 2' $nextZip
    Check-UserFile 'Heilung 2'
    Check-Running 'Heilung 2'
    Check 'Heilung 2: Update-Sicherung vor der Deinstallation vorhanden (wird Datei für Datei bereinigt)' (Test-Path "$install.backup\VERSION.txt")
    Check 'Heilung 3: Deinstallation' ((Uninstall) -eq 0)
    Check-Uninstalled 'Heilung 3'
    Check-UserFile 'Heilung 3'
}

if ($Mode -eq 'Blocked') {
    # From 1.20.1 the uninstaller renames <app>.backup and <app>.update-staging to *.erhalten before anything else, so
    # that the blanket rules of 1.20.0 that remain in unins000.dat find nothing. If a rename is impossible, it must
    # STOP before removing anything; it must never continue with such a folder under its old name.
    $old = Get-Release $OldTag @('*-setup.exe*')
    Check "Installation $OldTag" ((Install (Get-ChildItem "$old\*-setup.exe").FullName "$Out\install-old.log") -eq 0)
    New-UserFile "Blockiert ($OldTag)"
    $sha = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
    $code = Invoke-Updater @('-Archive', $zip, '-Sha256', $sha) "$Out\update-old-updater.log"
    Check "ZIP-Update mit dem Updater von $OldTag" ($code -eq 0 -and (Get-Content "$install\VERSION.txt").Trim() -eq $version) "Exit $code"
    Check 'Setup des Kandidaten über die aktualisierte Installation' ((Install $setup "$Out\install-candidate.log") -eq 0)
    Check-Installed 'Blockiert'
    Check 'Blockiert: Update-Sicherung des alten Updaters vorhanden' (Test-Path "$install.backup\VERSION.txt")
    $staging = "$install.update-staging"
    $relOwn = '_internal\qa-nur-in-der-sicherung.txt'; $relStaging = 'ECU-Studio-AI\_internal\qa-nur-im-staging.txt'
    'nur in der Sicherung' | Set-Content -Encoding utf8 "$install.backup\$relOwn"
    New-Item -ItemType Directory (Split-Path "$staging\$relStaging") -Force | Out-Null
    'nur im Staging' | Set-Content -Encoding utf8 "$staging\$relStaging"
    $ownHash = (Get-FileHash "$install.backup\$relOwn").Hash; $stagingHash = (Get-FileHash "$staging\$relStaging").Hash
    $programBefore = Get-TreeHash $install
    $backupBefore = Get-TreeHash "$install.backup"
    $stagingBefore = Get-TreeHash $staging

    $cases = @(
        @{ Label = 'Blockiert A (Sicherung gesperrt)'; Folder = "$install.backup"; File = "$install.backup\VERSION.txt"; Log = 'uninstall-blocked-a.log' },
        @{ Label = 'Blockiert B (Staging gesperrt, Sicherung schon umbenannt)'; Folder = $staging; File = "$staging\$relStaging"; Log = 'uninstall-blocked-b.log' })
    foreach ($case in $cases) {
        $label = $case.Label
        $lock = [System.IO.File]::Open($case.File, 'Open', 'Read', 'Read')   # no FileShare.Delete: rename impossible
        try {
            $renamed = $true
            try { [System.IO.Directory]::Move($case.Folder, "$($case.Folder)-probe") } catch { $renamed = $false }
            if ($renamed) { [System.IO.Directory]::Move("$($case.Folder)-probe", $case.Folder) }
            Check "$label`: Umbenennen nachweislich unmöglich (Probe)" (-not $renamed) $case.Folder
            $code = Uninstall-Blocked "$Out\$($case.Log)"
        } finally { $lock.Dispose() }
        $log = if (Test-Path "$Out\$($case.Log)") { Get-Content "$Out\$($case.Log)" -Raw } else { '' }
        Check "$label`: Deinstallation meldet Abbruch (Exit ungleich 0)" ($code -ne 0) "Exit $code"
        Check "$label`: Abbruch im Deinstallationsprotokoll" ($log -match 'DEINSTALLATION ABGEBROCHEN, nichts entfernt') (
            ($log -split "`n" | Where-Object { $_ -match 'umbenannt|ABGEBROCHEN|zur.{1,2}ckgenommen' }) -join ' | ')
        Check "$label`: Programmordner unverändert (SHA-256 aller Dateien)" (-not (Compare-Object $programBefore (Get-TreeHash $install)))
        Check "$label`: Sicherung unverändert unter ihrem Namen (SHA-256 aller Dateien)" (
            (Test-Path "$install.backup") -and -not (Compare-Object $backupBefore (Get-TreeHash "$install.backup")))
        Check "$label`: Staging unverändert unter seinem Namen" ((Test-Path $staging) -and -not (Compare-Object $stagingBefore (Get-TreeHash $staging)))
        Check "$label`: kein umbenannter Ordner (*.erhalten) übrig" (-not (Test-Path "$install.backup.erhalten*") -and -not (Test-Path "$staging.erhalten*"))
        Check-Installed $label
        Check-UserFile $label
        if ($case.Folder -eq $staging) {
            Check "$label`: Umbenennung der Sicherung zurückgenommen" ($log -match 'Ordner umbenannt .*\.backup -> .*\.backup\.erhalten' -and
                $log -match 'Umbenennung zur.{1,2}ckgenommen: .*\.backup\.erhalten -> .*\.backup')
        }
    }
    Check-Running 'nach blockierter Deinstallation'

    # Unlocked: the uninstallation runs. Own files stay, unchanged, in the renamed folders; nothing else of them.
    Check 'Blockiert C: Deinstallation ohne Sperre' ((Uninstall) -eq 0)
    $keptBackup = "$install.backup.erhalten"; $keptStaging = "$staging.erhalten"
    $backupLeft = @(Get-ChildItem $keptBackup -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName.Substring($keptBackup.Length + 1) })
    $stagingLeft = @(Get-ChildItem $keptStaging -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName.Substring($keptStaging.Length + 1) })
    Check 'Blockiert C: in ECU-Studio-AI.backup.erhalten genau die eigene Datei und ihr Inventar' (
        $backupLeft.Count -eq 2 -and -not (Compare-Object $backupLeft @('RUNTIME_INVENTORY.json', $relOwn)) -and
        (Get-FileHash "$keptBackup\$relOwn").Hash -eq $ownHash) ("$($backupLeft.Count): " + ($backupLeft -join ', '))
    Check 'Blockiert C: in ECU-Studio-AI.update-staging.erhalten genau die eigene Datei, unverändert' (
        $stagingLeft.Count -eq 1 -and $stagingLeft[0] -eq $relStaging -and (Get-FileHash "$keptStaging\$relStaging").Hash -eq $stagingHash) (
        "$($stagingLeft.Count): " + ($stagingLeft -join ', '))
    # Disposable runner only: the test removes what the uninstaller rightly kept, then checks everything else.
    foreach ($kept in @($keptBackup, $keptStaging)) { if (Test-Path -LiteralPath $kept) { Remove-Item -LiteralPath $kept -Recurse -Force } }
    Check-Uninstalled 'Blockiert C'
    Check-UserFile 'Blockiert C'
}

if ($Mode -eq 'Rollback') {
    # Failure handling of the installer route with the real setup of the next version.
    if (-not $Next) { throw '-Next fehlt' }
    Check 'Installation Kandidat' ((Install $setup "$Out\install.log") -eq 0)
    Check-Installed 'Rollback-Test'
    New-UserFile 'Rollback-Test'
    $before = Get-TreeHash $install
    $nextSha = (Get-FileHash $nextSetup -Algorithm SHA256).Hash.ToLower()

    $code = Invoke-Updater @('-Installer', $nextSetup, '-Sha256', ('0' * 64), '-ExpectedVersion', $nextVersion) "$Out\rollback-1.log"
    Check '1. falsche Prüfsumme: abgelehnt (Exit 2)' ($code -eq 2) "Exit $code"
    Check '1. nichts verändert (SHA-256 aller Dateien, keine Sicherung)' (-not (Compare-Object $before (Get-TreeHash $install)) -and
        -not (Test-Path "$install.backup") -and (Get-DisplayVersion) -eq $version) (Get-DisplayVersion)

    $code = Invoke-Updater @('-Installer', $nextSetup, '-Sha256', $nextSha, '-ExpectedVersion', '9.9.9') "$Out\rollback-2.log"
    Check '2. Fehler nach dem Setup (falsche Version): Rollback (Exit 3)' ($code -eq 3) "Exit $code"
    Check '2. Programmordner exakt wie vorher (SHA-256 aller Dateien)' (-not (Compare-Object $before (Get-TreeHash $install)))
    Check '2. Apps & Features zeigt wieder die installierte Version' ((Get-DisplayVersion) -eq $version) (Get-DisplayVersion)
    Check '2. keine Sicherungs- oder Fehlerordner übrig' (-not (Test-Path "$install.backup") -and -not (Test-Path "$install.update-failed"))
    Check-Running '2. nach Rollback'

    $code = Invoke-Updater @('-Installer', $nextSetup, '-Sha256', $nextSha, '-ExpectedVersion', $nextVersion) "$Out\rollback-3.log"
    Check '3. Update per Installer' ($code -eq 0) "Exit $code"
    Check-Installed '3. Update per Installer' $nextVersion
    Check-PackageInstalled '3. Update per Installer' $nextZip
    Check '3. Sicherung = vorherige Installation (SHA-256 aller Dateien)' (-not (Compare-Object $before (Get-TreeHash "$install.backup")))
    Check-UserFile '3. Update per Installer'

    $code = Invoke-Updater @('-Restore') "$Out\rollback-4.log"
    Check '4. vorherige Version wiederhergestellt' ($code -eq 0 -and -not (Compare-Object $before (Get-TreeHash $install))) "Exit $code"
    Check '4. Apps & Features zeigt die wiederhergestellte Version' ((Get-DisplayVersion) -eq $version) (Get-DisplayVersion)
    Check '4. ersetzte Version liegt als Sicherung bereit' ((Get-Content "$install.backup\VERSION.txt" -ErrorAction SilentlyContinue) -eq $nextVersion)
    Check-Running '4. nach Wiederherstellung'

    Check '5. Deinstallation' ((Uninstall) -eq 0)
    Check-Uninstalled '5. Deinstallation'
    Check-UserFile '5. Deinstallation'
}

Save-Results
if ($script:failed) { exit 1 }
exit 0
