#!/usr/bin/env bash
# Create or refresh the local, Git-ignored test environment for Composition.
set -euo pipefail

service_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_python="$service_dir/.venv/bin/python"

if [[ ! -x "$venv_python" ]]; then
  python3 -m venv "$service_dir/.venv"
fi

"$venv_python" -m pip install --upgrade pip
"$venv_python" -m pip install -r "$service_dir/requirements.txt" -r "$service_dir/requirements-test.txt"
"$venv_python" -m pip install -e "$service_dir/../../sdks/python[test]"

echo "Composition test environment is ready: $venv_python"
