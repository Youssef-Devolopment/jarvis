# JARVIS one-line installer
# ---------------------------------------------------------------
# Run from anywhere (PowerShell or cmd):
#   powershell -c "iex (irm https://raw.githubusercontent.com/Youssef-Devolopment/jarvis/main/setup.ps1)"
#
# What it does:
#   1. finds Python 3.10+ (py -3.10, py -3, or python)
#   2. clones the repo to %USERPROFILE%\jarvis (skipped when run
#      from inside an existing checkout, or when that folder
#      already holds a clone)
#   3. builds .venv and installs every requirement group + pip
#   4. installs Playwright Chromium (browser skills)
#   5. creates .env from .env.example (never overwrites)
#   6. sanity-checks the environment
#
# It does NOT start JARVIS, touch autostart, or modify .env values.
#
# Param (only used when cloning): -Path 'D:\somewhere\jarvis'

param(
    [string]$Path = (Join-Path $env:USERPROFILE 'jarvis')
)

$ErrorActionPreference = 'Stop'

function Step($m) { Write-Host "[..] $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[ok] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[~~] $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "[!!] $m" -ForegroundColor Red; throw $m }

# ---------- platform guard -------------------------------------------------
if ([Environment]::OSVersion.Platform -ne 'Win32NT') {
    Fail 'JARVIS only runs on Windows 10/11.'
}

# ---------- python 3.10+ ---------------------------------------------------
Step 'Looking for Python 3.10+'
$cands = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    $cands += , @('py', @('-3.10'))
    $cands += , @('py', @('-3'))
}
if (Get-Command python -ErrorAction SilentlyContinue) {
    $cands += , @('python', @())
}
$py = $null
foreach ($c in $cands) {
    try {
        $v = & $c[0] $c[1] -c 'import sys;print(sys.version_info[0]*100+sys.version_info[1])' 2>$null
        if ($LASTEXITCODE -eq 0 -and [int]$v -ge 310) { $py = $c; break }
    } catch { }
}
if (-not $py) {
    Fail 'Python 3.10+ not found. Install it from https://www.python.org/downloads/ (check "Add python.exe to PATH") and re-run.'
}
Ok ("Using " + (& $py[0] $py[1] -c 'import sys;print(sys.version)' 2>$null))

# ---------- locate or clone ------------------------------------------------
$root = $null
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'config.py'))) {
    $root = $PSScriptRoot
    Ok "Installing inside existing checkout: $root"
} elseif (Test-Path (Join-Path $Path '.git')) {
    $root = $Path
    Ok "Reusing existing clone: $root"
} else {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Fail 'Git not found. Install it from https://git-scm.com/download/win and re-run.'
    }
    if ((Test-Path $Path) -and (Get-ChildItem -Force $Path -ErrorAction SilentlyContinue)) {
        Fail "Target folder exists and is not a JARVIS clone: $Path (remove it or pass -Path <empty folder>)"
    }
    Step "Cloning https://github.com/Youssef-Devolopment/jarvis -> $Path"
    & git clone 'https://github.com/Youssef-Devolopment/jarvis.git' $Path
    if ($LASTEXITCODE -ne 0) { Fail 'git clone failed (network? proxy?).' }
    $root = $Path
}

# ---------- venv -----------------------------------------------------------
$venvPy = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    Step 'Creating virtualenv (.venv)'
    & $py[0] $py[1] -m venv (Join-Path $root '.venv')
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPy)) { Fail 'venv creation failed.' }
} else {
    Ok 'Reusing existing .venv'
}

# ---------- dependencies ---------------------------------------------------
Step 'Installing Python packages (a few minutes, wheels are cached when possible)'
& $venvPy -m pip install --upgrade pip --disable-pip-version-check -q
if ($LASTEXITCODE -ne 0) { Warn 'pip self-upgrade failed (continuing).' }
& $venvPy -m pip install -r (Join-Path $root 'requirements.txt') --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Fail 'pip install failed - see errors above.' }
Ok 'Python packages installed'

# open-interpreter must be added WITHOUT its own dependency resolution:
# its 0.4.3 metadata now contradicts itself (tiktoken<0.8 vs every modern
# litellm needing >=0.8) which makes pip backtrack to a source-only build
# and crash. Its working deps live in requirements-integrations.txt.
Step 'Installing open-interpreter (--no-deps; see requirements-integrations.txt)'
& $venvPy -m pip install --no-deps open-interpreter==0.4.3
if ($LASTEXITCODE -ne 0) { Fail 'open-interpreter install failed.' }

# ---------- chromium -------------------------------------------------------
Step 'Installing Playwright Chromium (browser skills)'
& $venvPy -m playwright install chromium
if ($LASTEXITCODE -ne 0) {
    Warn 'Chromium install failed - browser skills only, everything else works.'
} else {
    Ok 'Chromium ready'
}

# ---------- .env -----------------------------------------------------------
$envFile = Join-Path $root '.env'
$createdEnv = $false
if (-not (Test-Path $envFile)) {
    $tpl = Join-Path $root '.env.example'
    if (Test-Path $tpl) {
        Copy-Item $tpl $envFile
        $createdEnv = $true
        Ok '.env created from template'
    } else {
        Warn '.env.example missing - create .env manually.'
    }
} else {
    Ok '.env already exists (left untouched)'
}

# ---------- sanity check ---------------------------------------------------
Step 'Sanity-checking the environment'
Push-Location $root
try {
    & $venvPy -m pip check
    if ($LASTEXITCODE -ne 0) { Warn 'pip check reported conflicts (usually harmless).' }
} finally {
    Pop-Location
}

# ---------- post-install health ------------------------------------------
# check.py exit codes: 0 = ready (optional gaps reported as
# capabilities), 1 = core broken, 2 = key missing -> skills-only mode.
# A fresh install has a placeholder API key by design, so exit 2 is the
# EXPECTED first-install result — never fail the install over it.
Step 'Running post-install health check (informational)'
Push-Location $root
try {
    & $venvPy check.py
    $code = $LASTEXITCODE
    if ($code -eq 0) {
        Ok 'Preflight passed - JARVIS is ready to start.'
    } elseif ($code -eq 2) {
        Warn 'Core checks passed - JARVIS starts in skills-only mode (no key yet).'
        Write-Host '  AI chat unlocks with one step (no file editing):' -ForegroundColor Yellow
        Write-Host '    1. Start JARVIS:  desktop.bat'
        Write-Host '    2. Open Settings (gear) -> GENERAL -> paste key -> SAVE+TEST'
        Write-Host '  ...or edit .env by hand:  notepad .env'
    } else {
        Warn 'Core checks failed - fix the X items above, then re-run check.py.'
    }
} finally {
    Pop-Location
}

# ---------- summary --------------------------------------------------------
Write-Host ''
Ok "JARVIS installed at $root"
Write-Host ''
Write-Host '  1. Launch now (works WITHOUT any API key):' -ForegroundColor Yellow
Write-Host "       `"$root\desktop.bat`"   tray mode + Ctrl+Alt+J (recommended)"
Write-Host "       `"$root\start.bat`"     console server"
Write-Host '       -> starts in skills-only mode: local skills, memory,'
Write-Host '          reminders and the HUD all work out of the box.'
Write-Host '  2. Add an API key (unlocks AI chat):' -ForegroundColor Yellow
Write-Host '       Settings -> GENERAL -> paste DEEPSEEK_API_KEY -> SAVE+TEST'
Write-Host "       ...or: notepad `"$envFile`""
Write-Host '  3. Optional extras (all degrade gracefully when absent):' -ForegroundColor Yellow
Write-Host '       GROQ_API_KEY (mic)  TAVILY/BRAVE_API_KEY (search)'
Write-Host '       OBSIDIAN_VAULT (notes)  TODOIST_API_TOKEN (tasks)'
Write-Host ''
Write-Host '  Any time: run check.py   (0=ready, 1=fix core, 2=skills-only)' -ForegroundColor DarkGray
Write-Host ''
