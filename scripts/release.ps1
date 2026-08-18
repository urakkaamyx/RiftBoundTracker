<#
.SYNOPSIS
  Publishes a self-contained win-x64 build, zips it, and cuts a GitHub release.
.EXAMPLE
  .\scripts\release.ps1 -Version 1.0.1 -Notes "Fixed the scan crop region"
#>
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$Notes = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$proj = Join-Path $root "src\RiftBoundTracker.App\RiftBoundTracker.App.csproj"
$publishDir = Join-Path $root "publish\$Version"
$zipPath = Join-Path $root "publish\RiftBoundTracker-$Version-win-x64.zip"

Write-Host "== Bumping version to $Version ==" -ForegroundColor Cyan
(Get-Content $proj -Raw) -replace '<Version>[\d\.]+</Version>', "<Version>$Version</Version>" |
    Set-Content $proj -NoNewline

Write-Host "== Ensuring local AI model is present ==" -ForegroundColor Cyan
# The GGUF model (Ask Rules' local explanation layer) is deliberately not committed to git — a
# ~1GB binary would bloat the repo's history forever — so it's fetched here instead, straight into
# the csproj's Models/*.gguf publish-output item, so `dotnet publish` below bundles it into the
# release zip same as any other output file. Idempotent: does nothing if a dev already has it
# cached locally from a previous release (or from local Ask Rules testing).
$modelDir = Join-Path $root "src\RiftBoundTracker.App\Models"
$modelFile = "Qwen2.5-1.5B-Instruct-Q4_K_M.gguf"
$modelPath = Join-Path $modelDir $modelFile
$modelUrl = "https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/$modelFile"
$expectedBytes = 986048768
if (-not (Test-Path $modelDir)) { New-Item -ItemType Directory -Path $modelDir | Out-Null }
if ((Test-Path $modelPath) -and (Get-Item $modelPath).Length -eq $expectedBytes) {
    Write-Host "  (already present and verified)"
} else {
    if (Test-Path $modelPath) { Remove-Item $modelPath -Force }
    Write-Host "  Downloading $modelFile (~940 MB, one-time)..."
    Invoke-WebRequest -Uri $modelUrl -OutFile $modelPath
    $actualBytes = (Get-Item $modelPath).Length
    if ($actualBytes -ne $expectedBytes) {
        throw "Downloaded model size mismatch: expected $expectedBytes bytes, got $actualBytes. Aborting release rather than shipping a possibly-corrupt model."
    }
}

Write-Host "== Publishing self-contained win-x64 build ==" -ForegroundColor Cyan
# Deliberately NOT using -p:PublishSingleFile=true: it bundles every managed assembly (including
# Tesseract's own wrapper DLL) into the exe, which breaks its native-library loader (InteropDotNet
# resolves tesseract50.dll/leptonica via Assembly.Location, which is empty for a bundled assembly
# -> ArgumentNullException at OCR time). A plain self-contained publish (a folder of loose files,
# no separate .NET install needed) avoids the incompatibility entirely.
if (Test-Path $publishDir) { Remove-Item $publishDir -Recurse -Force }
dotnet restore $proj -r win-x64
if ($LASTEXITCODE -ne 0) { throw "Restore failed" }
dotnet publish $proj -c Release -r win-x64 --self-contained true --no-restore -o $publishDir
if ($LASTEXITCODE -ne 0) { throw "Publish failed" }

Write-Host "== Zipping ==" -ForegroundColor Cyan
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path "$publishDir\*" -DestinationPath $zipPath

Write-Host "== Committing any pending changes and tagging ==" -ForegroundColor Cyan
git -C $root add -A
$pending = git -C $root status --porcelain
if ($pending) {
    git -C $root commit -m "Release v$Version"
} else {
    Write-Host "  (nothing to commit — tagging the current HEAD)"
}
git -C $root tag "v$Version"
git -C $root push
git -C $root push --tags

Write-Host "== Creating GitHub release ==" -ForegroundColor Cyan
$releaseNotes = if ($Notes) { $Notes } else { "Release v$Version" }
gh release create "v$Version" $zipPath --title "v$Version" --notes "$releaseNotes"

# gh release create has occasionally left a release stuck in draft state (a draft won't show up
# via the public /releases/latest API the app's update-checker relies on) — force-publish as a
# safety net regardless.
gh release edit "v$Version" --draft=false

Write-Host "== Done: v$Version published ==" -ForegroundColor Green
