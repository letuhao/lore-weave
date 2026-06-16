#!/usr/bin/env sh
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/contracts/api/identity/v1"
# Spectral does not walk up to find a ruleset; point it at the repo ruleset
# explicitly so the gate actually lints instead of erroring with "No ruleset has
# been found". A path RELATIVE to the spec dir (../../../ = contracts/) is used
# deliberately — an absolute "$ROOT/..." path is mangled by WSL→Windows path
# translation on dev boxes; the relative form is portable across CI + local.
exec npx --yes @stoplight/spectral-cli lint --ruleset ../../../.spectral.yaml openapi.yaml
