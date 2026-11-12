# QA ONLY: collects one QA build (dist/) into a package folder for the installer test (installer-qa.yml).
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$Destination
)
$ErrorActionPreference = 'Stop'
$built = (Get-Content dist\ECU-Studio-AI\VERSION.txt).Trim()
if ($built -ne $Version) { throw "Build hat Version $built statt $Version" }
foreach ($name in @("ECU-Studio-AI-$Version-windows-x64.zip", "ECU-Studio-AI-$Version-setup.exe")) {
    $file = Join-Path dist $name
    if (-not (Test-Path "$file.sha256")) { throw "$name.sha256 fehlt" }
    $expected = ((Get-Content "$file.sha256") -split '\s+')[0]
    if ((Get-FileHash $file -Algorithm SHA256).Hash.ToLower() -ne $expected) { throw "$name passt nicht zu seiner .sha256" }
}
python -m ecu_studio.tools.release_notes "v$Version" --out dist\release-notes.md
if ($LASTEXITCODE -ne 0) { throw 'Release-Notes/Version passen nicht.' }
New-Item -ItemType Directory $Destination -Force | Out-Null
Copy-Item "dist\ECU-Studio-AI-$Version-*" $Destination
Copy-Item dist\release-notes.md, dist\ECU-Studio-AI\VERSION.txt, dist\ECU-Studio-AI\RUNTIME_INVENTORY.json $Destination
Get-ChildItem $Destination | ForEach-Object { Write-Host "$($_.Name)  $($_.Length)" }
