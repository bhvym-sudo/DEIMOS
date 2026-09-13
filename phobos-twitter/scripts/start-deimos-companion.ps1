$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$deimosRoot = Split-Path -Parent $projectRoot
$appDataRoot = Join-Path $env:APPDATA "t-rex-osint"
$runtimePath = Join-Path $appDataRoot "config\runtime.json"
$profilePath = Join-Path $appDataRoot "sessions\x_edge_profile"
$envFile = Join-Path $deimosRoot ".env"

if (-not (Test-Path -LiteralPath $runtimePath)) { throw "T-REX session metadata was not found at $runtimePath" }
if (-not (Test-Path -LiteralPath $profilePath)) { throw "T-REX Edge profile was not found at $profilePath" }
if (-not (Test-Path -LiteralPath $envFile)) { throw "DEIMOS .env file was not found at $envFile" }

$tokenLine = Get-Content -LiteralPath $envFile | Where-Object { $_ -like "PHOBOS_TWITTER_API_TOKEN=*" } | Select-Object -First 1
if (-not $tokenLine) { throw "PHOBOS_TWITTER_API_TOKEN is missing from the DEIMOS .env file" }

$env:PHOBOS_TWITTER_API_TOKEN = $tokenLine.Substring($tokenLine.IndexOf("=") + 1).Trim()
$env:TREX_DATA_DIR = $projectRoot
$env:TREX_SESSION_SOURCE = $runtimePath
Remove-Item Env:TREX_RUNTIME_PATH -ErrorAction SilentlyContinue
$env:TREX_SESSION_DIR = $profilePath
$env:TREX_PYTHON_WORKER = Join-Path $projectRoot "python_worker\search_timeline.py"
$env:TREX_ACCOUNT_WORKER = Join-Path $projectRoot "python_worker\account_lookup.py"
$env:PHOBOS_TWITTER_ADDR = "0.0.0.0:8791"
$env:PHOBOS_TWITTER_DIRECT_SEARCH = "1"

Write-Host "PHOBOS-Tweeter companion is using the authenticated T-REX AppData session."
Write-Host "Keep this window open while using DEIMOS. Listening securely on port 8791."
Set-Location -LiteralPath $projectRoot
go run ./backend/cmd/trex
