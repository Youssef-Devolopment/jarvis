# JARVIS one-line installer
# ---------------------------------------------------------------
# Run from anywhere (PowerShell or cmd):
#   powershell -NoProfile -ExecutionPolicy Bypass -Command "iex (iwr https://raw.githubusercontent.com/Youssef-Devolopment/jarvis/main/setup.ps1 -UseBasicParsing).Content"
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

# ---------- summary --------------------------------------------------------
Write-Host ''
Ok "JARVIS installed at $root"
Write-Host ''
if ($createdEnv) {
    Write-Host '  1. Add your API keys :' -ForegroundColor Yellow
    Write-Host "       notepad `"$envFile`""
    Write-Host '       (DEEPSEEK_API_KEY at minimum; see .env.example)'
}
Write-Host '  2. Launch JARVIS     :' -ForegroundColor Yellow
Write-Host "       `"$root\desktop.bat`"   tray mode + Ctrl+Alt+J (recommended)"
Write-Host "       `"$root\start.bat`"     console server on http://127.0.0.1:5000"
Write-Host ''
