#!/usr/bin/env bash
# L1.K.6 observability-inventory-lint.sh — SR12 I19
#
# Every `lw_*` metric emitted from code MUST have a matching entry in
# contracts/observability/inventory.yaml. This lint enforces by:
#   1. grep all `lw_*` literal symbol references in Go/Rust source
#   2. read the inventory yaml (key = metric name)
#   3. flag any code-emitted symbol not declared in inventory
#
# Exit 0 = clean; 1 = violations.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
inventory="$repo_root/contracts/observability/inventory.yaml"

if [[ ! -f "$inventory" ]]; then
  echo "[observability-inventory] WARN — no inventory.yaml; skipping"
  exit 0
fi

# Collect declared metric names (key under `metrics:` block)
declared=$(grep -E '^[[:space:]]*-[[:space:]]*name:[[:space:]]*"?lw_' "$inventory" 2>/dev/null \
  | sed -E 's/.*name:[[:space:]]*"?([a-zA-Z0-9_]+)"?.*/\1/' | sort -u || true)

# Collect emitted metric names from code.
# Pattern: prom metric names follow lw_<subsystem>_<verb>(_<unit>?) — at least
# 2 underscore-separated segments after `lw_`. Single-segment names like
# `lw_reality_000…` are typically DB-name format strings, not metrics.
#
# Cycle 19 (L4.H) refinement: exclude *_test.go and *_test.rs because test
# files legitimately reference fake/fixture metric names (e.g.,
# `lw_test_registered_total`, `lw_foo_bar_total`) for admission-control
# unit tests. The lint MUST only fire on REAL emission sites in non-test
# code.
#
# 2026-08-09 — THAT EXCLUSION WAS GO-SHAPED, AND THIS LINT ALSO READS RUST.
# `*_test.rs` is not where Rust unit tests live; they live INLINE, in a
# `#[cfg(test)] mod tests { … }` block inside the source file. So the rule
# above enforced its stated intent ("only REAL emission sites in non-test
# code") for Go and not for Rust, and nothing said so until a Rust file put
# fixtures in one.
#
# What surfaced it: `services/world-service/src/orphan_scan.rs` names its
# fixture databases readably — `lw_reality_ok`, `lw_reality_ghost`,
# `lw_reality_stalled`, … — all inside the `#[cfg(test)]` module at line 252.
# The DB-name filter below excludes `lw_reality_` + HEX (the real convention,
# `lw_reality_cd0747d24b94`), so six test fixtures were reported as six
# undeclared METRICS.
#
# That is `NV-4`, the hardest shape: two individually correct decisions
# defeating a third. Readable fixture names are right for a test; a hex-only
# DB-name filter is right for production; a Go-shaped test exclusion was right
# when the lint only read Go. And the failure mode was the expensive
# direction — the "fix" it invites is to declare six metrics that do not
# exist, which would have put a fiction in the observability inventory and
# turned the gate green.
#
# So the fix is the root: strip `#[cfg(test)]` blocks from Rust sources before
# scanning, which is what the 2019 comment above always meant.
emitted=$(python3 - "$repo_root" <<'PY'
import re, sys
from pathlib import Path

root = Path(sys.argv[1])
LITERAL = re.compile(r'"(lw_[a-z][a-z0-9]*_[a-z][a-z0-9_]+)"')


def strip_cfg_test(text: str) -> str:
    """Remove `#[cfg(test)] mod … { … }` blocks, matched by brace depth.

    Brace counting rather than a regex because the block is nested and a
    regex cannot balance. Strings and comments containing braces would fool
    a naive counter, so this deliberately errs toward stripping LESS: if the
    opening brace is never found, nothing is removed and the file is scanned
    whole. Under-stripping produces a false positive someone must look at;
    over-stripping produces a blind spot nobody sees.
    """
    out, i = [], 0
    while True:
        m = re.compile(r'#\[cfg\(test\)\]').search(text, i)
        if not m:
            out.append(text[i:])
            return "".join(out)
        out.append(text[i:m.start()])
        brace = text.find("{", m.end())
        if brace == -1:
            out.append(text[m.start():])
            return "".join(out)
        depth, j = 0, brace
        while j < len(text):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        i = j + 1


found = set()
for sub in ("services", "crates", "contracts"):
    base = root / sub
    if not base.is_dir():
        continue
    for path in base.rglob("*"):
        if path.suffix not in (".go", ".rs") or not path.is_file():
            continue
        if path.name.endswith(("_test.go", "_test.rs")):
            continue
        # RUST INTEGRATION TESTS live in a `tests/` DIRECTORY, not in files
        # named `*_test.rs`. That naming rule is Go's, and this is the SECOND
        # time it has been applied to Rust here: the first produced six false
        # positives from `#[cfg(test)]` blocks, fixed by `strip_cfg_test` above,
        # and the same Go-shaped assumption left a whole directory uncovered.
        # Found 2026-08-09 by `crates/dp-control-plane/tests/surface.rs`, whose
        # fixture db_name `lw_reality_surface` was read as an undeclared metric.
        #
        # `tests/` is cargo's own definition of a test target, so this is a
        # STRUCTURAL exclusion rather than an allowlist — a test file added
        # tomorrow is covered without anyone remembering to add it. It excludes
        # only test targets: a metric emitted solely from a test is not a metric
        # the inventory should declare, which is the whole reason test code was
        # being excluded already.
        if any(part == "tests" for part in path.parts):
            continue
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if path.suffix == ".rs":
            body = strip_cfg_test(body)
        found.update(LITERAL.findall(body))

for name in sorted(found):
    print(name)
PY
)

# Filter out DB-name format strings (lw_reality_*) and other known non-metric
# patterns; these are matched by the broader regex but aren't metric names.
# Kept NARROW (hex only) on purpose: widening it to `lw_reality_[a-z0-9_]+`
# would silently swallow a genuine future metric in that namespace, which is
# the blind spot the fix above exists to avoid creating.
emitted=$(echo "$emitted" | grep -vE '^lw_reality_[0-9a-f]+$' | grep -vE '^lw_reality_$' || true)

violations=0
for sym in $emitted; do
  if ! echo "$declared" | grep -qx "$sym"; then
    echo "[observability-inventory] FAIL — $sym emitted from code but NOT declared in inventory.yaml"
    violations=$((violations + 1))
  fi
done

if [[ $violations -gt 0 ]]; then
  echo "[observability-inventory] FAIL — $violations metric(s) missing inventory entry (SR12 I19)"
  exit 1
fi
echo "[observability-inventory] PASS"
exit 0
