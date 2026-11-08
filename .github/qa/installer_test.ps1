<#
Installer test of a release candidate on a FRESH, isolated Windows runner (never on a developer machine:
it installs, starts, uninstalls and changes per-user settings).

  -Mode Fresh   clean system: install, Start menu and desktop start, icon, version, self-test, GUI smoke,
                end-to-end check with the installed runtime, restart, uninstall, leftovers, reinstall
  -Mode Update  published 1.19.1 installed and used first, then the candidate installed over it; user data,
                settings and another (portable) ECU Studio copy must stay untouched; also the in-app updater path
  -Mode InApp   published old version installed, started from the Start menu and updated FROM ITS OWN MENU
                (UI Automation); release source = staging server on this runner (staging_server.py)

Writes $Out\results.json; exit code 1 if any check failed.
#>
param(
    [Parameter(Mandatory = $true)][ValidateSet('Fresh', 'Update', 'InApp')][string]$Mode,
    [Parameter(Mandatory = $true)][string]$Package,
    [Parameter(Mandatory = $true)][string]$Out,
    [string]$Repository = 'PCTestAdmin/ECU-Studio-AI',
    [string]$OldTag = 'v1.19.1',
    [string]$QaPython = ''
)
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
    # The uninstaller continues in a temporary copy; wait until it removed the program folder.
    for ($i = 0; $i -lt 120 -and (Test-Path "$install\ECU-Studio-AI.exe"); $i++) { Start-Sleep -Milliseconds 500 }
    for ($i = 0; $i -lt 60 -and (Get-Process -Name '_iu*' -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Milliseconds 500 }
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
function Check-Installed([string]$Label) {
    Check "$Label`: Programm installiert" (Test-Path "$install\ECU-Studio-AI.exe") $install
    Check "$Label`: Version" ((Get-Content "$install\VERSION.txt").Trim() -eq $version) (Get-Content "$install\VERSION.txt")
    $key = Get-ItemProperty $uninstallKey -ErrorAction SilentlyContinue
    Check "$Label`: Eintrag in Apps & Features" ($key -and $key.DisplayVersion -eq $version -and $key.DisplayIcon -like "*ECU-Studio-AI.exe") `
        "$($key.DisplayName) $($key.DisplayVersion)"
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
    Check '4. Deinstallation' ((Uninstall) -eq 0)
    $diff = Compare-Object $before (Get-Snapshot) | ForEach-Object { "$($_.SideIndicator) $($_.InputObject)" }
    Check 'nach zweiter Deinstallation nichts zurück' (-not $diff) ($diff -join '; ')
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
    $leftover = @(Get-ChildItem $install -Recurse -File -Force | ForEach-Object { $_.FullName.Substring($install.Length + 1) } |
        Where-Object { -not $zipFiles.ContainsKey($_) -and $_ -notmatch '^unins000\.(exe|dat)$' })
    Check 'Update: Restdateien der alten Version (nur Information)' $true "$($leftover.Count): $($leftover -join ', ')"
    Check 'Update: Selbsttest' ((Run-Exe @('--self-check')) -eq 0)
    $code = Run-Exe @('--smoke-test', ('"' + "$Out\gui-smoke-update" + '"'))
    $smoke = if (Test-Path "$Out\gui-smoke-update\gui-smoke.json") { Get-Content "$Out\gui-smoke-update\gui-smoke.json" -Raw -Encoding utf8 | ConvertFrom-Json }
    Check 'Update: GUI-Smoke-Test inkl. Checksummen' ($code -eq 0 -and $smoke.passed -and $smoke.checksums) "Exit $code"
    E2E $install 'compat' "$Out\user" 'Update: Projekt und Einstellungen aus 1.19.1'
    E2E $install 'first' "$Out\e2e" 'Update: Ablauf'
    Check 'Update: Projekt und BIN des Benutzers unverändert' (-not (Compare-Object $userBefore ($userFiles | ForEach-Object { (Get-FileHash $_).Hash })))
    Check 'Update: private Datei in .ecu_studio_ai unverändert' ((Get-FileHash "$HOME\.ecu_studio_ai\qa-private-note.txt").Hash -eq $noteBefore)

    Check 'Deinstallation nach Update' ((Uninstall) -eq 0)
    Check 'Programmordner entfernt' (-not (Test-Path $install))
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
    # Real in-app update: the published old version is installed with its installer, used, started from the Start
    # menu and updated from its own menu. The release source is a STAGING server on this runner (see
    # staging_server.py); no tag and no GitHub release are created.
    if (-not $QaPython) { throw '-QaPython fehlt' }
    $old = Join-Path $Out 'old'
    gh release download $OldTag --repo $Repository --pattern '*-setup.exe*' --dir $old
    foreach ($file in Get-ChildItem "$old\*.sha256") {
        $expected = ((Get-Content $file.FullName) -split '\s+')[0]
        $target = $file.FullName -replace '\.sha256$', ''
        Check "Download $OldTag geprüft: $(Split-Path $target -Leaf)" ((Get-FileHash $target -Algorithm SHA256).Hash.ToLower() -eq $expected)
    }
    $oldVersion = $OldTag.TrimStart('v')
    Check "Installation $OldTag" ((Install (Get-ChildItem "$old\*-setup.exe").FullName "$Out\install-old.log") -eq 0)
    Check "$OldTag installiert" ((Get-Content "$install\VERSION.txt").Trim() -eq $oldVersion)
    E2E $install 'seed' "$Out\user" "Benutzerdaten mit $OldTag angelegt"
    New-Item -ItemType Directory "$HOME\.ecu_studio_ai" -Force | Out-Null
    'private Notiz des Benutzers' | Set-Content -Encoding utf8 "$HOME\.ecu_studio_ai\qa-private-note.txt"
    $userFiles = @("$Out\user\alt.ecustudio", "$Out\user\alt.bin")
    $userBefore = $userFiles | ForEach-Object { (Get-FileHash $_).Hash }
    $noteBefore = (Get-FileHash "$HOME\.ecu_studio_ai\qa-private-note.txt").Hash
    $oldTree = Get-TreeHash $install

    $staging = Join-Path $Out 'staging'
    $hosts = "$env:SystemRoot\System32\drivers\etc\hosts"
    $hostsBefore = Get-Content $hosts -Raw
    $server = $null; $caThumb = $null
    try {
        $server = Start-Process $QaPython -ArgumentList @('-I', ('"' + "$qa\staging_server.py" + '"'), ('"' + $staging + '"'),
            ('"' + (Resolve-Path $Package) + '"'), $Repository) -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput "$Out\staging.out" -RedirectStandardError "$Out\staging.err"
        for ($i = 0; $i -lt 60 -and -not (Test-Path "$staging\ready"); $i++) { Start-Sleep -Milliseconds 500 }
        Check 'Staging-Quelle läuft (nur auf diesem Runner)' (Test-Path "$staging\ready") (Get-Content "$Out\staging.err" -Raw -ErrorAction SilentlyContinue)
        $caThumb = (Import-Certificate "$staging\ca.cer" -CertStoreLocation Cert:\LocalMachine\Root).Thumbprint
        Add-Content $hosts "`r`n127.0.0.1 api.github.com`r`n127.0.0.1 github.com"
        ipconfig /flushdns | Out-Null
        # Probe with the update code of the INSTALLED old version (its runtime, Windows trust store).
        $probe = & "$install\_internal\python\python.exe" -I -B -c "from ecu_studio.core import updates; r = updates.fetch_latest(); print(r.version if r else 'none', updates.update_available('$oldVersion', r))" 2>&1
        Check 'Staging-Quelle: alte Version sieht den Kandidaten als neueste stabile Version' ("$probe".Trim() -eq "$version True") "$probe"

        Start-Process $startMenuLink
        $proc = $null
        for ($i = 0; $i -lt 180 -and -not $proc; $i++) {
            Start-Sleep -Milliseconds 500
            $proc = Get-Process pythonw -ErrorAction SilentlyContinue |
                Where-Object { $_.Path -like "$install\*" -and $_.MainWindowTitle -like "*v$oldVersion*" } | Select-Object -First 1
        }
        Check "$OldTag über das Startmenü gestartet" $proc $(if ($proc) { $proc.MainWindowTitle } else { 'kein Hauptfenster' })
        Start-Sleep -Seconds 3
        $p = Start-Process $QaPython -ArgumentList @('-I', ('"' + "$qa\inapp_ui.py" + '"'), "$($proc.Id)", ('"' + "$Out\inapp" + '"'),
            $oldVersion, $version) -PassThru -Wait -WindowStyle Hidden -RedirectStandardOutput "$Out\inapp-ui.out" -RedirectStandardError "$Out\inapp-ui.err"
        $ui = if (Test-Path "$Out\inapp\inapp-ui.json") { Get-Content "$Out\inapp\inapp-ui.json" -Raw -Encoding utf8 | ConvertFrom-Json }
        foreach ($c in @($ui.checks)) { if ($c) { Check "In-App-Update (Bedienung) / $($c.name)" $c.ok $c.detail } }
        Check 'In-App-Update (Bedienung, Prozess)' ($p.ExitCode -eq 0 -and $ui.passed) ("Exit $($p.ExitCode) " + $(if ($ui.error) { $ui.error.Split("`n")[-2] }))

        # The updater (started by the old version) waits for it to end, installs, self-checks and restarts.
        $new = $null
        for ($i = 0; $i -lt 600 -and -not $new; $i++) {
            Start-Sleep -Milliseconds 500
            $new = Get-Process pythonw -ErrorAction SilentlyContinue |
                Where-Object { $_.Path -like "$install\*" -and $_.MainWindowTitle -like "*v$version*" } | Select-Object -First 1
        }
        $log = Get-Content "$env:LOCALAPPDATA\ECUStudioAI\updates\update.log" -Raw -Encoding utf8 -ErrorAction SilentlyContinue
        Copy-Item "$env:LOCALAPPDATA\ECUStudioAI\updates\update.log" "$Out\inapp-update.log" -ErrorAction SilentlyContinue
        Check 'Updater: installiert, Selbsttest, Neustart' ($log -match 'Update installiert') (($log -split "`n" | Select-Object -Last 3) -join ' | ')
        Check "Neustart als $version (Fenstertitel)" $new $(if ($new) { $new.MainWindowTitle } else { 'kein Fenster' })
        if ($new) {
            Start-Sleep -Seconds 3
            Screenshot "$Out\inapp-5-neue-version.png"
            E2E $install 'window' "$Out\window-inapp" 'Fenster nach In-App-Update' @("$($new.Id)") $false
            $null = $new.CloseMainWindow()
            Check 'neue Version beendet sich normal' ($new.WaitForExit(30000))
        }
        $requests = @(Get-Content "$staging\requests.log" -ErrorAction SilentlyContinue | ForEach-Object { $_ | ConvertFrom-Json })
        Check 'Programm hat Release-Info, .sha256 und ZIP von der Staging-Quelle geladen' (
            @($requests | Where-Object { $_.status -eq 200 -and $_.path -like '*/releases/latest' }).Count -ge 1 -and
            @($requests | Where-Object { $_.status -eq 200 -and $_.path -like '*.zip.sha256' }).Count -ge 1 -and
            @($requests | Where-Object { $_.status -eq 200 -and $_.path -like '*.zip' }).Count -ge 1) (($requests | ForEach-Object { "$($_.status) $($_.path)" }) -join '; ')
    } catch {
        Check 'In-App-Ablauf ohne Ausnahme' $false $_.Exception.Message
    } finally {
        Set-Content $hosts $hostsBefore -NoNewline
        ipconfig /flushdns | Out-Null
        if ($caThumb) { Remove-Item "Cert:\LocalMachine\Root\$caThumb" -ErrorAction SilentlyContinue }
        if ($server) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
        Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$install*" } | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    Check 'Staging entfernt (hosts wiederhergestellt, Test-CA gelöscht)' ((Get-Content $hosts -Raw) -eq $hostsBefore -and
        -not ($caThumb -and (Test-Path "Cert:\LocalMachine\Root\$caThumb")))

    Check 'nach In-App-Update: Version' ((Get-Content "$install\VERSION.txt").Trim() -eq $version) (Get-Content "$install\VERSION.txt")
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
    Check 'nach In-App-Update: alle Dateien des Kandidaten (SHA-256)' ($wrong.Count -eq 0) "$($zipFiles.Count) Dateien, abweichend: $($wrong -join ', ')"
    Check 'nach In-App-Update: Sicherung der alten Version vorhanden' ((Get-Content "$install.backup\VERSION.txt" -ErrorAction SilentlyContinue) -eq $oldVersion -and
        -not (Compare-Object $oldTree (Get-TreeHash "$install.backup")))
    Check 'nach In-App-Update: Deinstallationsprogramm erhalten' ((Test-Path "$install\unins000.exe") -and (Test-Path "$install\unins000.dat"))
    $key = Get-ItemProperty $uninstallKey -ErrorAction SilentlyContinue
    Check 'Apps & Features: Versionsanzeige nach In-App-Update (nur Information)' $true "$($key.DisplayName) / DisplayVersion $($key.DisplayVersion)"
    Check 'nach In-App-Update: Selbsttest' ((Run-Exe @('--self-check')) -eq 0)
    $code = Run-Exe @('--smoke-test', ('"' + "$Out\gui-smoke-inapp" + '"'))
    $smoke = if (Test-Path "$Out\gui-smoke-inapp\gui-smoke.json") { Get-Content "$Out\gui-smoke-inapp\gui-smoke.json" -Raw -Encoding utf8 | ConvertFrom-Json }
    Check 'nach In-App-Update: GUI-Smoke-Test inkl. Checksummen' ($code -eq 0 -and $smoke.passed -and $smoke.checksums) "Exit $code"
    E2E $install 'compat' "$Out\user" "nach In-App-Update: Projekt und Einstellungen aus $OldTag"
    Check 'nach In-App-Update: Projekt und BIN des Benutzers unverändert' (-not (Compare-Object $userBefore ($userFiles | ForEach-Object { (Get-FileHash $_).Hash })))
    Check 'nach In-App-Update: private Datei in .ecu_studio_ai unverändert' ((Get-FileHash "$HOME\.ecu_studio_ai\qa-private-note.txt").Hash -eq $noteBefore)

    Check 'Deinstallation nach In-App-Update' ((Uninstall) -eq 0)
    $left = @(Get-ChildItem $install -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName.Substring($install.Length + 1) })
    $left | Set-Content -Encoding utf8 "$Out\leftovers-after-uninstall.txt"
    Check 'Programmordner und Update-Sicherung entfernt' (-not (Test-Path $install) -and -not (Test-Path "$install.backup")) `
        ("$($left.Count) Dateien übrig: " + (($left | Select-Object -First 12) -join ', '))
    Check 'Benutzerdaten nach Deinstallation erhalten' ((Get-FileHash "$HOME\.ecu_studio_ai\qa-private-note.txt").Hash -eq $noteBefore)
}

Save-Results
if ($script:failed) { exit 1 }
exit 0
