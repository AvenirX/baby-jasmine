# Baby Jasmine - Windows Setup & Dependency Checker
# Double-click via setup_jasmine.bat, or run in PowerShell.
# Usage: .\setup_windows.ps1 [-NoWecom] [-WithDev] [-Launch]
param(
    [switch]$NoWecom,   # skip wecom extra (websockets, pycryptodome, etc.)
    [switch]$WithDev,   # include pytest + ruff
    [switch]$Launch     # after successful setup, hand off to start_wecom.ps1
)

# ── Helpers ───────────────────────────────────────────────────────────────────
# $script:errors must be initialised before any function that appends to it.
$script:errors = @()

function Write-Step { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "    [OK]  $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "    [!!]  $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "    [ERR] $msg" -ForegroundColor Red; $script:errors += $msg }

# Prepend uv install locations and reload registry PATH without losing
# any process-level additions that were already in $env:Path.
function Sync-Path {
    $machine = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $user    = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $uv      = "$env:USERPROFILE\.local\bin;$env:USERPROFILE\.cargo\bin"
    $env:Path = "$uv;$machine;$user;$env:Path"
}

# Use $PSScriptRoot (robust for -File invocations) with a fallback.
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $scriptDir) { Write-Fail "Cannot determine script directory"; exit 1 }
Set-Location $scriptDir

# Pre-warm PATH so uv is reachable if already installed but not in current PATH.
Sync-Path

# ── 1. Python 3.11+ ───────────────────────────────────────────────────────────
Write-Step "Checking Python 3.11+"
$py = $null
foreach ($cmd in @("python3.12", "python3.11", "python3", "python")) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if (-not $found) { continue }
    # Skip Microsoft Store stub (opens the Store instead of running Python).
    if ($found.Source -match 'WindowsApps') { continue }
    $ver = & $cmd --version 2>&1
    if ($LASTEXITCODE -eq 0 -and $ver -match '^Python 3\.(1[1-9]|[2-9]\d)\b') {
        $py = $cmd; break
    }
}

if (-not $py) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Fail "Python 3.11+ not found and winget is unavailable. Download from https://www.python.org/downloads/"
    } else {
        Write-Warn "Python 3.11+ not found - attempting install via winget..."
        winget install --id Python.Python.3.12 --source winget --silent `
            --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "winget Python install failed (exit $LASTEXITCODE). Download from https://www.python.org/downloads/"
        } else {
            Sync-Path
            $ver = python --version 2>&1
            if ($LASTEXITCODE -eq 0 -and $ver -match '^Python 3\.(1[1-9]|[2-9]\d)\b') {
                $py = "python"; Write-Ok "Installed: $ver"
            } else {
                Write-Fail "Python installed but not found on PATH after refresh. Restart this script."
            }
        }
    }
} else {
    Write-Ok "Found $py ($ver)"
}

# ── 2. Git (needed for wecom-aibot git dependency) ────────────────────────────
Write-Step "Checking Git"
$gitCmd = Get-Command git -ErrorAction SilentlyContinue
if ($gitCmd) {
    $gitVer = git --version 2>&1
    Write-Ok $gitVer
} else {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Fail "Git not found and winget is unavailable. Download from https://git-scm.com/download/win"
    } else {
        Write-Warn "Git not found - attempting install via winget..."
        winget install --id Git.Git --source winget --silent `
            --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "winget Git install failed (exit $LASTEXITCODE). Download from https://git-scm.com/download/win"
        } else {
            Sync-Path
            $gitCmd2 = Get-Command git -ErrorAction SilentlyContinue
            if ($gitCmd2) { Write-Ok "Installed: $(git --version 2>&1)" }
            else { Write-Fail "Git installed but not on PATH. Restart this script." }
        }
    }
}

# ── 3. uv ─────────────────────────────────────────────────────────────────────
Write-Step "Checking uv"
$uvOk = $false
$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if ($uvCmd) {
    $uvVer = uv --version 2>&1
    Write-Ok $uvVer
    $uvOk = $true
} else {
    Write-Warn "uv not found - installing via official installer..."
    try {
        $installer = Invoke-RestMethod https://astral.sh/uv/install.ps1
        # Run in a child scriptblock so the installer's own 'exit' call cannot
        # terminate this script if it encounters an error.
        & ([scriptblock]::Create($installer))
        Sync-Path
        $uvCmd2 = Get-Command uv -ErrorAction SilentlyContinue
        if ($uvCmd2) {
            Write-Ok "Installed: $(uv --version 2>&1)"
            $uvOk = $true
        } else {
            Write-Fail "uv installer ran but uv is not on PATH. Restart this script."
        }
    } catch {
        Write-Fail "uv install failed: $_. Visit https://docs.astral.sh/uv/getting-started/installation/"
    }
}

# ── 4. Config files ───────────────────────────────────────────────────────────
Write-Step "Setting up config files"

if (-not (Test-Path "config\agent.yaml")) {
    if (Test-Path "config\agent.example.yaml") {
        Copy-Item "config\agent.example.yaml" "config\agent.yaml"
        Write-Ok "Created config\agent.yaml from example"
        Write-Warn "Edit config\agent.yaml before running (LLM provider, WeCom settings)"
    } else {
        Write-Fail "config\agent.example.yaml not found - is this the project root?"
    }
} else {
    Write-Ok "config\agent.yaml exists"
}

if (-not (Test-Path ".env")) {
    # Write UTF-8 without BOM so python-dotenv does not misread the first key.
    $template = "# Baby Jasmine credentials - fill in before running`n# OCEAN_SCENE_ID=`n# WECOM_BOT_ID=`n# WECOM_BOT_SECRET=`n"
    [System.IO.File]::WriteAllText(
        (Join-Path (Get-Location) ".env"),
        $template,
        (New-Object System.Text.UTF8Encoding $false)
    )
    Write-Ok "Created .env placeholder"
    Write-Warn "Edit .env and add your API credentials"
} else {
    Write-Ok ".env exists"
}
# Always check for filled-in values - warns whether the file is new or old.
$envContent = Get-Content ".env" -Raw -ErrorAction SilentlyContinue
$filledLines = ($envContent -split "`n") | Where-Object { $_ -match '^\s*[^#\s].*=\S' }
if ($filledLines.Count -eq 0) {
    Write-Warn ".env has no filled-in credentials - bot will likely fail at runtime"
}

# ── 5. Data directories ───────────────────────────────────────────────────────
Write-Step "Ensuring data directories"
foreach ($dir in @("data\transcripts", "data\memory", "skills")) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Ok "Created $dir"
    } else {
        Write-Ok "$dir exists"
    }
}

# ── 6. Python dependencies ────────────────────────────────────────────────────
Write-Step "Installing Python dependencies"

if ($uvOk) {
    $extras = @()
    if (-not $NoWecom) { $extras += "--extra", "wecom" }
    if ($WithDev)      { $extras += "--extra", "dev" }

    # --frozen: install exactly what uv.lock specifies without re-resolving.
    $syncArgs = @("sync", "--frozen") + $extras
    Write-Host "    Running: uv $($syncArgs -join ' ')"

    uv @syncArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "uv sync failed (exit $LASTEXITCODE)"
    } else {
        Write-Ok "All packages installed"
    }
} else {
    Write-Fail "Skipped - uv is not available"
}

# ── 7. Smoke-test the entry point ─────────────────────────────────────────────
Write-Step "Verifying baby-jasmine entry point"
if ($uvOk -and $script:errors.Count -eq 0) {
    uv run baby-jasmine --help 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "Entry point works"
    } else {
        Write-Warn "baby-jasmine --help failed (exit $LASTEXITCODE) - check manually"
    }
} else {
    Write-Warn "Skipped (earlier errors present)"
}

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host ""

if ($script:errors.Count -gt 0) {
    Write-Host "Setup finished with $($script:errors.Count) error(s):" -ForegroundColor Red
    $script:errors | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "Fix the issues above and re-run setup_jasmine.bat." -ForegroundColor Yellow
    Read-Host "`nPress Enter to exit"
    exit 1
}

Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""

if ($Launch) {
    $startScript = Join-Path $scriptDir "start_wecom.ps1"
    if (Test-Path $startScript) {
        Write-Host "Handing off to start_wecom.ps1..." -ForegroundColor Cyan
        Write-Host ""
        & $startScript
    } else {
        Write-Warn "start_wecom.ps1 not found - launching directly"
        uv run baby-jasmine --wecom --project-root .
        if ($LASTEXITCODE -ne 0) { Read-Host "`nBot exited with error. Press Enter to close" }
    }
} else {
    Write-Host "Next steps:" -ForegroundColor White
    Write-Host "  1. Edit config\agent.yaml  - LLM provider, model, WeCom settings"
    Write-Host "  2. Edit .env               - OCEAN_SCENE_ID and/or WECOM_* credentials"
    Write-Host "  3. Double-click start_wecom.bat to launch the bot"
    Write-Host ""
    Write-Host "Other run options:"
    Write-Host "  uv run baby-jasmine --wecom --project-root ."
    Write-Host "  uv run baby-jasmine --local --project-root ."
    Write-Host ""
    Read-Host "Press Enter to exit"
}
