#!/bin/sh
# Source installer: builds for this OS, installs for this user, then starts Dock.
set -eu
cd "$(dirname "$0")"
PYTHON="${DOCK_BUILD_PYTHON:-python3}"
"$PYTHON" -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11 or later is required"'
"$PYTHON" -m venv build/install-venv
build/install-venv/bin/python -m pip install --upgrade pip
build/install-venv/bin/python -m pip install '.[build]'
exec build/install-venv/bin/python scripts/build_app.py --install "$@"
