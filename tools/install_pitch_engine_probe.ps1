param(
    [ValidateSet(
        "pitch_engine_probe",
        "pitch_order_probe",
        "pitch_fraction_probe",
        "pitch_overlap_probe",
        "timeline_sync_probe"
    )]
    [string]$ProbeName = "pitch_engine_probe"
)

$ErrorActionPreference = "Stop"

$probe = Join-Path $PSScriptRoot "..\examples\$ProbeName.rawmap.json"
$loaderDirectory = Join-Path $env:LOCALAPPDATA "snapmap-plus"
$destination = Join-Path $loaderDirectory "rawmap.json"

New-Item -ItemType Directory -Force -Path $loaderDirectory | Out-Null

if (Test-Path -LiteralPath $destination) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backup = Join-Path $loaderDirectory "rawmap.before-pitch-probe-$stamp.json"
    Copy-Item -LiteralPath $destination -Destination $backup
    Write-Host "Backed up the existing map to:"
    Write-Host "  $backup"
}

Copy-Item -LiteralPath $probe -Destination $destination
Write-Host "Installed the pitch probe at:"
Write-Host "  $destination"
