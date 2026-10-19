<#
    JARVIS — build the virtual environment and install dependencies.

    Run by the installer after the files are copied, and re-runnable by
    hand afterwards (it is idempotent, so a failed run can simply be
    repeated):

        powershell -ExecutionPolicy Bypass -File installer\install-deps.ps1

    Rules it keeps:
      * it only ever writes inside the install folder
      * it never overwrites an existing .env
      * every step it prints also lands in logs\install.log, and the
        dependency output is tee'd there too, so a failure report has
        something to point at
#>
[CmdletBinding()]
param(
    [string]$AppDir,
    [switch]$SkipPlaywright,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$started = Get-Date

if (-not $AppDir) {
    $AppDir = Split-Path -Parent $PSScriptRoot
}
$AppDir = (Resolve-Path -LiteralPath $AppDir).Path
$logDir = Join-Path $AppDir 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'install.log'

function Say {
    param([string]$Message, [string]$Colour = 'Gray')
    Write-Host $Message -ForegroundColor $Colour
    try {
        Add-Content -LiteralPath $log -Value ("[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $Message)
    } catch {
        # A logging failure must never be the reason an install fails.
    }
}

function Fail {
    param([string]$Message)
    Say "  [x] $Message" 'Red'
    Say "  Log: $log" 'Red'
    exit 1
}

# Runs a command, streams it to the console AND appends it to the log,
# and returns its exit code.
function Invoke-Logged {
    param([string]$Exe, [string[]]$Arguments)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $Exe @Arguments 2>&1 | Tee-Object -LiteralPath $log -Append | Out-Host
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previous
    return $code
}

function Test-Python {
    param([string]$Exe, [string[]]$Prefix)
    try {
        $output = & $Exe @Prefix '--version' 2>&1
        if ($LASTEXITCODE -ne 0) { return $null }
        $text = ($output | Out-String).Trim()
        if ($text -match 'Python (\d+)\.(\d+)') {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -eq 3 -and $minor -ge 10) { return $text }
        }
    } catch {
        return $null
    }
    return $null
}

Say ''
Say '  JARVIS setup' 'White'
Say "  folder: $AppDir" 'DarkGray'
Say ''

# -- 1. Python --------------------------------------------------------
$candidates = @(
    @{ Exe = 'py';     Prefix = @('-3.10') },
    @{ Exe = 'py';     Prefix = @('-3')    },
    @{ Exe = 'python'; Prefix = @()        }
)
$chosen = $null
foreach ($candidate in $candidates) {
    $version = Test-Python -Exe $candidate.Exe -Prefix $candidate.Prefix
    if ($version) {
        $chosen = @{ Exe = $candidate.Exe; Prefix = $candidate.Prefix; Version = $version }
        break
    }
}
if (-not $chosen) {
    Fail 'Python 3.10 or newer was not found. Install it from https://www.python.org/downloads/ and run this script again.'
}
Say "  found $($chosen.Version) via '$($chosen.Exe) $($chosen.Prefix -join ' ')'" 'Green'

# -- 2. Virtual environment -------------------------------------------
$venv = Join-Path $AppDir '.venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'

if ($Force -and (Test-Path -LiteralPath $venv)) {
    Say '  -Force: removing the existing virtual environment' 'Yellow'
    Remove-Item -LiteralPath $venv -Recurse -Force
}

if (Test-Path -LiteralPath $venvPython) {
    Say '  virtual environment already present - reusing it' 'DarkGray'
} else {
    Say '  creating the virtual environment...' 'Cyan'
    & $chosen.Exe @($chosen.Prefix) -m venv $venv 2>&1 |
        Tee-Object -LiteralPath $log -Append | Out-Host
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
        Fail "could not create a virtual environment at $venv"
    }
}

# -- 3. Dependencies --------------------------------------------------
Say '  upgrading pip...' 'Cyan'
if ((Invoke-Logged $venvPython @('-m', 'pip', 'install', '--upgrade', 'pip',
        '--disable-pip-version-check', '--quiet')) -ne 0) {
    Fail 'pip could not be upgraded - is there an internet connection?'
}

Say '  installing requirements (a few minutes on a cold cache)...' 'Cyan'
if ((Invoke-Logged $venvPython @('-m', 'pip', 'install', '-r',
        (Join-Path $AppDir 'requirements.txt'), '--disable-pip-version-check')) -ne 0) {
    Fail 'dependency installation failed - the reason is in the output above'
}

Say '  installing open-interpreter (--no-deps: its own pins are broken, see requirements-integrations.txt)...' 'Cyan'
if ((Invoke-Logged $venvPython @('-m', 'pip', 'install', '--no-deps',
        'open-interpreter==0.4.3', '--disable-pip-version-check')) -ne 0) {
    # Optional integration: warn, do not fail the install.
    Say '  [warn] open-interpreter did not install; the agent features that use it stay off' 'Yellow'
}

# -- 4. Browser engine (optional) -------------------------------------
if ($SkipPlaywright) {
    Say '  skipping the browser engine - browsing skills stay off until it is installed' 'DarkGray'
    Say '         add it later with:  .venv\Scripts\python.exe -m playwright install chromium' 'DarkGray'
} else {
    Say '  installing the browser engine (Playwright Chromium)...' 'Cyan'
    if ((Invoke-Logged $venvPython @('-m', 'playwright', 'install', 'chromium')) -ne 0) {
        Say '  [warn] Playwright Chromium did not install; browsing skills will say so' 'Yellow'
    }
}

# -- 5. .env ----------------------------------------------------------
$envFile = Join-Path $AppDir '.env'
$example = Join-Path $AppDir '.env.example'
if ((Test-Path -LiteralPath $example) -and (-not (Test-Path -LiteralPath $envFile))) {
    Copy-Item -LiteralPath $example -Destination $envFile
    Say '  created .env from .env.example - JARVIS runs on local skills with no key at all' 'Green'
} elseif (Test-Path -LiteralPath $envFile) {
    Say '  .env already exists - left exactly as it was' 'DarkGray'
}

# -- 6. Prove it imports ----------------------------------------------
Say '  verifying the environment...' 'Cyan'
$probe = 'import flask, config; print("flask", flask.__version__, "| jarvis", config.VERSION)'
if ((Invoke-Logged $venvPython @('-c', $probe)) -ne 0) {
    Fail 'the environment cannot import the app - see the log'
}

$elapsed = [int]((Get-Date) - $started).TotalSeconds
Say ''
Say "  [ok] ready in ${elapsed}s" 'Green'
Say '       launch it with the JARVIS shortcut, or:  .venv\Scripts\pythonw.exe desktop.py' 'Gray'
Say '       dashboard:  http://127.0.0.1:5000   (change PORT in .env)' 'Gray'
Say ''
exit 0
