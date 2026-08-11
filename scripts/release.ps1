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

Write-Host "== Publishing self-contained win-x64 build ==" -ForegroundColor Cyan
if (Test-Path $publishDir) { Remove-Item $publishDir -Recurse -Force }
dotnet publish $proj -c Release -r win-x64 --self-contained true `
    -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true `
    -o $publishDir
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

Write-Host "== Done: v$Version published ==" -ForegroundColor Green
