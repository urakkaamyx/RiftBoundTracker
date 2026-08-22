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
# The Ask Rules GGUF model is NOT part of this build — it's a separate, much-more-stable asset
# (RiftKeep's own fine-tuned Qwen2.5-1.5B, hosted under the "ask-rules-model-v1" tag; see
# scripts/training/README.md to publish a new one) that the app fetches into App_Data at runtime
# via LocalAiModelService, the first time Ask Rules' local AI is enabled. Keeping it out of every
# app release is the whole point: a one-line CSS fix used to mean re-zipping and re-uploading the
# same ~940MB blob every single time.
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

# The bug-report GitHub token stays empty in source (appsettings.json is committed and public) —
# it's stamped into the PUBLISHED output only, read from an environment variable so it never
# touches git history. Set it once per shell: $env:RIFTKEEP_BUG_REPORT_TOKEN = "github_pat_...".
# Missing env var just means this build ships with bug reporting disabled, not a failed release.
$bugReportToken = $env:RIFTKEEP_BUG_REPORT_TOKEN
if ($bugReportToken) {
    Write-Host "== Stamping bug-report token into published build ==" -ForegroundColor Cyan
    $publishedSettings = Join-Path $publishDir "appsettings.json"
    $settingsJson = Get-Content $publishedSettings -Raw | ConvertFrom-Json
    $settingsJson.BugReport.GitHubToken = $bugReportToken
    $settingsJson | ConvertTo-Json -Depth 10 | Set-Content $publishedSettings
} else {
    Write-Host "== RIFTKEEP_BUG_REPORT_TOKEN not set — this build ships with bug reporting disabled ==" -ForegroundColor Yellow
}

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
# Default to the matching CHANGELOG.md section instead of a generic "Release vX" string, so the
# GitHub release notes stay in sync with the changelog without anyone having to remember to pass
# -Notes by hand (that's how v1.17.0/v1.18.0 ended up with real changelog entries in-repo but
# blank-looking release pages). -Notes still overrides this when explicitly passed.
function Get-ChangelogSection([string]$version) {
    $changelogPath = Join-Path $root "CHANGELOG.md"
    if (-not (Test-Path $changelogPath)) { return $null }
    $lines = Get-Content $changelogPath
    $escaped = [regex]::Escape($version)
    $startIndex = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^## v$escaped(\s|$)") { $startIndex = $i; break }
    }
    if ($startIndex -eq -1) { return $null }
    $endIndex = $lines.Count - 1
    for ($i = $startIndex + 1; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^## v') { $endIndex = $i - 1; break }
    }
    # Drop the "## vX — Title" header line itself; gh's --title already carries the version, and
    # the release page renders its own heading above the notes body.
    $body = $lines[($startIndex + 1)..$endIndex] -join "`n"
    return $body.Trim()
}
$releaseNotes = if ($Notes) { $Notes } else { Get-ChangelogSection $Version }
if (-not $releaseNotes) { $releaseNotes = "Release v$Version" }
gh release create "v$Version" $zipPath --title "v$Version" --notes "$releaseNotes"

# gh release create has occasionally left a release stuck in draft state (a draft won't show up
# via the public /releases/latest API the app's update-checker relies on) — force-publish as a
# safety net regardless.
gh release edit "v$Version" --draft=false

Write-Host "== Done: v$Version published ==" -ForegroundColor Green
