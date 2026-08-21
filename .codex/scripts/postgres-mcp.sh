#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/../.." && pwd)"

if [[ -f "$project_root/.envrc" ]]; then
  # Project-local secrets and connection strings are intentionally Git-ignored.
  # shellcheck disable=SC1091
  source "$project_root/.envrc"
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is not configured; create $project_root/.envrc" >&2
  exit 1
fi

exec npx -y @modelcontextprotocol/server-postgres "$DATABASE_URL"
