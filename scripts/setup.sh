#!/usr/bin/env bash
# One-time setup for map-shorts: venv + python deps + data + fonts.
set -e
cd "$(dirname "$0")/.."
ROOT=$(pwd)

need() { command -v "$1" >/dev/null 2>&1 || { echo "MISSING: $1  ($2)"; MISSING=1; }; }
MISSING=0
need python3 "install Python 3.10+"
need ffmpeg  "apt install ffmpeg | brew install ffmpeg | pacman -S ffmpeg"
[ "$MISSING" = 1 ] && exit 1

if [ ! -d .venv ]; then
  # system site packages lets a distro-provided pycairo be reused
  python3 -m venv --system-site-packages .venv
fi
PY=.venv/bin/python
$PY -m pip install -q --upgrade pip
$PY -m pip install -q -r requirements.txt || true
if ! $PY -c "import cairo" 2>/dev/null; then
  echo "pycairo failed to build. Install the cairo dev package, then re-run:"
  echo "  Debian/Ubuntu: sudo apt install libcairo2-dev pkg-config python3-dev"
  echo "  Fedora:        sudo dnf install cairo-devel pkgconf-pkg-config python3-devel"
  echo "  Arch:          sudo pacman -S cairo python-cairo"
  echo "  macOS:         brew install cairo pkg-config"
  exit 1
fi
$PY -m pip install -q -r requirements-optional.txt || echo "(optional deps failed: tts/align may not work)"
$PY scripts/fetch_data.py
$PY -c "import cairo, numpy, PIL; print('map-shorts ready:', '$ROOT')"
