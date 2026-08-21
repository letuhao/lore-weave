#!/usr/bin/env bash
# Run Composition tests with the service-local virtual environment.
set -euo pipefail

service_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_python="$service_dir/.venv/bin/python"

if [[ ! -x "$venv_python" ]]; then
  echo "Composition test environment is missing." >&2
  echo "Run: $service_dir/scripts/bootstrap-test-venv.sh" >&2
  exit 2
fi

cd "$service_dir"
exec "$venv_python" -m pytest "$@"
