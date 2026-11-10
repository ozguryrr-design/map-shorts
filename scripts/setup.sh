#!/usr/bin/env bash
# One-time setup for map-shorts: venv + python deps + data + fonts.
# Linux / macOS / WSL, and Git Bash on Windows (PowerShell users: scripts/setup.ps1).
set -e
cd "$(dirname "$0")/.."
ROOT=$(pwd)

case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) WIN=1 ;; *) WIN=0 ;; esac

# first Python 3.10+ that actually runs (on Windows "python3" may be the Microsoft Store stub)
SYSPY=""
for c in python3 python "py -3"; do
  if $c -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then SYSPY="$c"; break; fi
done

MISSING=0
if [ -z "$SYSPY" ]; then
  echo "MISSING: Python 3.10+  (apt/brew/pacman | Windows: winget install Python.Python.3.12)"; MISSING=1
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "MISSING: ffmpeg  (apt install ffmpeg | brew install ffmpeg | pacman -S ffmpeg | Windows: winget install Gyan.FFmpeg, then open a new terminal)"
  MISSING=1
fi
[ "$MISSING" = 1 ] && exit 1

if [ "$WIN" = 1 ]; then PY=.venv/Scripts/python.exe; else PY=.venv/bin/python; fi
if [ ! -x "$PY" ]; then
  if [ "$WIN" = 1 ]; then
    $SYSPY -m venv .venv
  else
    # system site packages lets a distro-provided pycairo be reused
    $SYSPY -m venv --system-site-packages .venv
  fi
fi
$PY -m pip install -q --upgrade pip
$PY -m pip install -q -r requirements.txt || true
if ! $PY -c "import cairo" 2>/dev/null; then
  echo "pycairo failed to build. Install the cairo dev package, then re-run:"
  echo "  Debian/Ubuntu: sudo apt install libcairo2-dev pkg-config python3-dev"
  echo "  Fedora:        sudo dnf install cairo-devel pkgconf-pkg-config python3-devel"
  echo "  Arch:          sudo pacman -S cairo python-cairo"
  echo "  macOS:         brew install cairo pkg-config"
  echo "  Windows:       pip uses a prebuilt wheel - use 64-bit CPython 3.10+ from python.org/winget"
  echo "                 (not Microsoft Store/MSYS/conda), delete .venv and re-run"
  exit 1
fi
$PY -m pip install -q -r requirements-optional.txt || echo "(optional deps failed: tts/align may not work)"
$PY scripts/fetch_data.py
$PY -c "import cairo, numpy, PIL; print('map-shorts ready:', '$ROOT')"
echo "Run commands with: $PY make.py ..."
