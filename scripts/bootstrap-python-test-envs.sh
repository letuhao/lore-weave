#!/usr/bin/env bash
# Create or refresh isolated test environments for every Python service.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON_BIN:-python3}"
services=(
  campaign-service
  chat-service
  composition-service
  jobs-service
  knowledge-service
  learning-service
  lore-enrichment-service
  translation-service
  video-gen-service
  worker-ai
)

usage() {
  printf 'Usage: %s [service ...]\n' "$(basename "$0")"
  printf 'Without arguments, prepares every Python service test environment.\n'
  printf 'Known services: %s\n' "${services[*]}"
}

contains_service() {
  local candidate="$1"
  local service
  for service in "${services[@]}"; do
    [[ "$service" == "$candidate" ]] && return 0
  done
  return 1
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

selected=("${services[@]}")
if (($# > 0)); then
  selected=("$@")
fi

for service in "${selected[@]}"; do
  if ! contains_service "$service"; then
    printf 'Unknown Python service: %s\n' "$service" >&2
    usage >&2
    exit 2
  fi

  service_dir="$repo_root/services/$service"
  venv_python="$service_dir/.venv/bin/python"
  requirements=("$service_dir/requirements.txt")
  if [[ -f "$service_dir/requirements-test.txt" ]]; then
    requirements+=("$service_dir/requirements-test.txt")
  fi

  if [[ ! -x "$venv_python" ]]; then
    "$python_bin" -m venv "$service_dir/.venv"
  fi

  PIP_DISABLE_PIP_VERSION_CHECK=1 "$venv_python" -m pip install 'setuptools>=68'
  pip_requirements=()
  for requirement in "${requirements[@]}"; do
    pip_requirements+=(-r "$requirement")
  done
  (
    cd "$service_dir"
    "$venv_python" -m pip install "${pip_requirements[@]}"
  )
  "$venv_python" -m pip install --no-build-isolation -e "$repo_root/sdks/python[test]"
done

printf 'Python test environments are ready.\n'
