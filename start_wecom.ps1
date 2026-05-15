# Baby Jasmine - WeCom launcher
# Quick pre-flight check, then runs: uv run baby-jasmine --wecom --project-root .
# Called by start_wecom.bat (double-click) or by setup_windows.ps1 -Launch.

$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $scriptDir) { Write-Host "[ERR] Cannot determine script directory" -ForegroundColor Red; Read-Host "Press Enter to exit"; exit 1 }
Set-Location $scriptDir

# Ensure uv is reachable even right after a fresh install.
$uv = "$env:USERPROFILE\.local\bin;$env:USERPROFILE\.cargo\bin"
$env:Path = "$uv;$env:Path"

function Write-Step { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "    [OK]  $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "    [!!]  $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "    [ERR] $msg" -ForegroundColor Red }

# ── Pre-flight ────────────────────────────────────────────────────────────────
Write-Step "Pre-flight check"
$ok = $true

$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if ($uvCmd) {
    Write-Ok "uv: $(uv --version 2>&1)"
} else {
    Write-Fail "uv not found - run setup_jasmine.bat first"
    $ok = $false
}

if (-not (Test-Path "config\agent.yaml")) {
    Write-Fail "config\agent.yaml missing - run setup_jasmine.bat first"
    $ok = $false
} else {
    Write-Ok "config\agent.yaml found"
}

if (-not (Test-Path ".env")) {
    Write-Warn ".env not found - bot may fail if credentials are required"
} else {
    Write-Ok ".env found"
    $envContent = Get-Content ".env" -Raw -ErrorAction SilentlyContinue
    $filledLines = ($envContent -split "`n") | Where-Object { $_ -match '^\s*[^#\s].*=\S' }
    if ($filledLines.Count -eq 0) {
        Write-Warn ".env has no filled-in credentials - bot will likely fail at runtime"
    }
}

if (-not $ok) {
    Write-Host ""
    Read-Host "Setup is incomplete. Press Enter to exit"
    exit 1
}

# ── Launch ────────────────────────────────────────────────────────────────────
Write-Step "Starting Baby Jasmine (WeCom mode)"
Write-Host "    Press Ctrl+C to stop the bot" -ForegroundColor Yellow
Write-Host ""

uv run baby-jasmine --wecom --project-root .
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Host ""
    Write-Fail "Baby Jasmine exited with code $exitCode"
    Read-Host "Press Enter to close"
    exit $exitCode
}
