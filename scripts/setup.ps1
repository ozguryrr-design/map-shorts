# One-time setup for map-shorts on Windows (PowerShell): venv + python deps + data + fonts.
#
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -InstallFfmpeg   # also installs ffmpeg via winget
#
# Afterwards run commands with the venv python:  .venv\Scripts\python make.py ...
param([switch]$InstallFfmpeg)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Fail($msg) {
    Write-Host $msg -ForegroundColor Red
    exit 1
}

# --- Python 3.10+ (skips the Microsoft Store "python3" stub, which only opens the Store) ---
$SysPy = $null
foreach ($cand in @(@("py", "-3"), @("python"), @("python3"))) {
    if (-not (Get-Command $cand[0] -ErrorAction SilentlyContinue)) { continue }
    $pyArgs = @($cand | Select-Object -Skip 1)
    $out = & $cand[0] @pyArgs -c "import sys; print(1 if sys.version_info >= (3, 10) else 0)" 2>$null
    if ($LASTEXITCODE -eq 0 -and "$out".Trim() -eq "1") { $SysPy = $cand; break }
}
if (-not $SysPy) {
    Fail ("MISSING: Python 3.10+ (64-bit).`n" +
          "  winget install Python.Python.3.12`n" +
          "  or https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then open a new terminal.")
}

# --- ffmpeg ---
function Update-PathFromRegistry {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    if ($InstallFfmpeg) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            Fail "winget not found. Install ffmpeg manually: https://www.gyan.dev/ffmpeg/builds/ (add its bin folder to PATH)."
        }
        Write-Host "installing ffmpeg (winget, Gyan.FFmpeg) ..."
        winget install --id Gyan.FFmpeg -e
        Update-PathFromRegistry
    }
    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
        Fail ("MISSING: ffmpeg`n" +
              "  winget install Gyan.FFmpeg      (then open a NEW terminal and re-run this script)`n" +
              "  or re-run with:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -InstallFfmpeg")
    }
}

# --- venv + dependencies ---
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    $pyArgs = @($SysPy | Select-Object -Skip 1)
    & $SysPy[0] @pyArgs -m venv .venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Py)) { Fail "could not create .venv" }
}
& $Py -m pip install -q --upgrade pip
& $Py -m pip install -q -r requirements.txt
& $Py -c "import cairo" 2>$null
if ($LASTEXITCODE -ne 0) {
    Fail ("pycairo failed to install. On Windows pip uses a prebuilt wheel, which needs a 64-bit`n" +
          "CPython 3.10+ from python.org or winget (not the Microsoft Store / MSYS / conda Python).`n" +
          "Delete the .venv folder and re-run this script with such a Python.")
}
& $Py -m pip install -q -r requirements-optional.txt
if ($LASTEXITCODE -ne 0) { Write-Host "(optional deps failed: tts/align may not work)" -ForegroundColor Yellow }

# --- data + fonts ---
& $Py scripts\fetch_data.py
if ($LASTEXITCODE -ne 0) { Fail "data download failed (network?) - re-run this script" }

& $Py -c "import cairo, numpy, PIL; print('map-shorts ready:', r'$Root')"
Write-Host "Run commands with:  .venv\Scripts\python make.py ..." -ForegroundColor Green
