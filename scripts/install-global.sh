#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."
uv tool install --editable "." --force
uv tool update-shell || true

echo "Installed ssh-manage globally."
echo "If your current shell cannot find it yet, open a new shell or source your shell profile."
