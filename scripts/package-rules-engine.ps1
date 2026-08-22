<#
.SYNOPSIS
  Packages the RiftKeep Rules Engine (rules-engine/) with a portable, no-install-needed Python
  runtime into a single zip, and optionally publishes it as a GitHub release asset.
.DESCRIPTION
  RiftKeep fetches this bundle into App_Data the first time Ask Rules is used (same
  fetch-on-first-use pattern as the local-AI GGUF model) rather than shipping it in the base
  install or requiring the end user to have Python installed. This script is a one-time-per-engine-
  version authoring step run by a developer, not something that runs on an end user's machine —
  once the resulting bundle is downloaded, running it needs no network access, matching the
  engine's own "normal serving requires no network" design.
.EXAMPLE
  .\scripts\package-rules-engine.ps1 -EngineVersion 1.0.0
.EXAMPLE
  .\scripts\package-rules-engine.ps1 -EngineVersion 1.0.0 -Publish -Notes "Stable 1.0 release"
#>
param(
    [Parameter(Mandatory = $true)][string]$EngineVersion,
    [string]$PythonVersion = "3.12.7",
    [switch]$Publish,
    [string]$Notes = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$engineSource = Join-Path $root "rules-engine"
$stagingDir = Join-Path $root "publish\rules-engine-staging"
$bundleDir = Join-Path $stagingDir "RulesEngine"
$zipPath = Join-Path $root "publish\RiftKeepRulesEngine-$EngineVersion-win-x64.zip"

if (-not (Test-Path $engineSource)) {
    throw "rules-engine/ not found at $engineSource — extract the engine milestone there first."
}

Write-Host "== Cleaning staging area ==" -ForegroundColor Cyan
if (Test-Path $stagingDir) { Remove-Item $stagingDir -Recurse -Force }
New-Item -ItemType Directory -Path $bundleDir -Force | Out-Null

Write-Host "== Copying engine source ==" -ForegroundColor Cyan
# riftkeep.py self-check validates against the certified release's own file manifest (built by
# build_stable_release_manifest.py) — trimming "dev-only" files here broke that check outright
# (confirmed directly: self-check reported "ok": false with every individual check passing, only
# the manifest completeness check failing). tests/ and docs/ together are 428KB against a 107MB
# package, so there's no real size win worth trading away release-integrity verification for.
$excludeDirs = @(".venv", "__pycache__")
Get-ChildItem $engineSource -Force | Where-Object {
    -not ($_.PSIsContainer -and $excludeDirs -contains $_.Name)
} | ForEach-Object {
    Copy-Item $_.FullName -Destination $bundleDir -Recurse -Force
}

Write-Host "== Downloading portable Python $PythonVersion (embeddable, no install needed) ==" -ForegroundColor Cyan
$pythonDir = Join-Path $bundleDir "python"
New-Item -ItemType Directory -Path $pythonDir -Force | Out-Null
$embedZipUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$embedZipPath = Join-Path $stagingDir "python-embed.zip"
Invoke-WebRequest -Uri $embedZipUrl -OutFile $embedZipPath
Expand-Archive -Path $embedZipPath -DestinationPath $pythonDir -Force

Write-Host "== Enabling site-packages on the embeddable runtime ==" -ForegroundColor Cyan
# The embeddable distribution ships with site-packages disabled by default (it's meant for
# minimal embedding scenarios) - re-enable it so `pip install` actually has somewhere to put
# PyMuPDF, and so riftkeep.py's own imports resolve normally.
$pthFile = Get-ChildItem $pythonDir -Filter "python3*._pth" | Select-Object -First 1
if (-not $pthFile) { throw "Could not find the embeddable runtime's ._pth file under $pythonDir" }
(Get-Content $pthFile.FullName) -replace '^#import site$', 'import site' | Set-Content $pthFile.FullName

Write-Host "== Bootstrapping pip ==" -ForegroundColor Cyan
$getPipPath = Join-Path $stagingDir "get-pip.py"
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPipPath
& "$pythonDir\python.exe" $getPipPath --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "pip bootstrap failed" }

Write-Host "== Installing engine dependencies (PyMuPDF) ==" -ForegroundColor Cyan
& "$pythonDir\python.exe" -m pip install --no-warn-script-location "PyMuPDF>=1.24"
if ($LASTEXITCODE -ne 0) { throw "Dependency install failed" }

Write-Host "== Self-check before packaging ==" -ForegroundColor Cyan
Push-Location $bundleDir
& "$pythonDir\python.exe" riftkeep.py self-check
$selfCheckOk = $LASTEXITCODE -eq 0
Pop-Location
if (-not $selfCheckOk) { throw "riftkeep.py self-check failed — do not package a broken engine" }

Write-Host "== Zipping ==" -ForegroundColor Cyan
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path "$bundleDir" -DestinationPath $zipPath

Write-Host "== Done: $zipPath ==" -ForegroundColor Green

if ($Publish) {
    Write-Host "== Publishing GitHub release rules-engine-v$EngineVersion ==" -ForegroundColor Cyan
    $releaseNotes = if ($Notes) { $Notes } else { "RiftKeep Rules Engine $EngineVersion" }
    gh release create "rules-engine-v$EngineVersion" $zipPath --title "Rules Engine v$EngineVersion" --notes "$releaseNotes"
    gh release edit "rules-engine-v$EngineVersion" --draft=false
    Write-Host "== Published ==" -ForegroundColor Green
}
