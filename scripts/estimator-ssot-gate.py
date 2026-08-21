#!/usr/bin/env python
"""D-ESTIMATOR-SSOT (spec §7 item 5) — one token estimator, or a stated reason to be a second.

Why this is a gate and not a refactor
-------------------------------------
The DoD line reads "one **context-budget** estimator (the billing convention stays separate,
with the reason recorded)". The parenthesis is the whole design: there are legitimately TWO
conventions on this platform and collapsing them would be a bug, not a cleanup.

Measured 2026-08-02, five implementations across four languages:

  sdks/python/loreweave_context/tokens.py         the script-aware KERNEL
  services/translation-service/.../chunk_splitter  ALREADY delegates to the kernel (S11)
  services/knowledge-service/.../token_counter     tiktoken BPE, exact where installed
  services/lore-enrichment-service/app/jobs/tokens BILLING — mirrors provider-registry
  services/provider-registry-service/.../estimate.go   the billing convention ITSELF

So the honest state is not "four copies to merge". Two are already one; one is a deliberately
separate convention with its counterpart in Go; and the fourth is STRICTLY MORE ACCURATE than
the kernel it would be folded into — knowledge's counter uses a real BPE encoding, and this
run measured the kernel at ~0.78x tiktoken on Vietnamese. Merging knowledge INTO the kernel
would make a context-window count worse, and merging the kernel into tiktoken changes chunk
sizes (and therefore per-chapter cost) everywhere, which is a decision with a price tag rather
than a tidy-up.

What can be mechanised is the thing that actually rots: a FIFTH appearing. Every estimator
here is registered with the reason it is not the kernel, and an unregistered one fails.

    python scripts/estimator-ssot-gate.py
    python scripts/estimator-ssot-gate.py --list
    python scripts/estimator-ssot-gate.py --self-test
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Where an estimator may live, and WHY it is not simply the kernel. An empty reason is a
#: failure: the point of the registry is the justification, not the listing.
SANCTIONED: dict[str, str] = {
    "sdks/python/loreweave_context/tokens.py":
        "THE KERNEL. Script-aware per-character factors; the one every context-budget "
        "consumer should reach for.",
    "services/translation-service/app/workers/chunk_splitter.py":
        "A DELEGATOR, not a second implementation — it calls the kernel and re-exports under "
        "its historical name because five modules import it from here (S11).",
    "services/knowledge-service/app/context/formatters/token_counter.py":
        "tiktoken BPE (o200k_base), with a len/4 fallback when tiktoken is absent. STRICTLY "
        "MORE ACCURATE than the kernel heuristic — measured at ~1.28x it on Vietnamese — so "
        "folding this into the kernel would make a context-window count worse, not cleaner. "
        "Converging the other way (kernel adopts tiktoken) changes chunk sizes, and therefore "
        "per-chapter LLM cost, everywhere: a decision with a price tag, not a tidy-up.",
    "services/lore-enrichment-service/app/jobs/tokens.py":
        "THE BILLING CONVENTION, deliberately separate per spec §7 item 5. Mirrors "
        "provider-registry's `EstimateTokens` (chars/1.0 for CJK, chars/3.5 for Latin) so an "
        "in-branch estimate agrees with what the platform actually charges. A context budget "
        "and a bill are different questions about the same text.",
    "services/provider-registry-service/internal/billing/estimate.go":
        "The billing convention itself, in Go, at the place that charges for it. The Python "
        "row above exists to MIRROR this one.",
}

#: Function names that count tokens. Matched at definition, per language.
_PATTERNS = (
    re.compile(r"^\s*def\s+_?(?:estimate|count)_tokens\s*\(", re.M),          # Python
    re.compile(r"^\s*func\s+(?:\(\w+\s+\*?\w+\)\s+)?(?:Estimate|Count)Tokens\s*\(", re.M),  # Go
    re.compile(r"^\s*(?:pub\s+)?fn\s+(?:estimate|count)_tokens\s*[(<]", re.M),  # Rust
    re.compile(r"^\s*(?:export\s+)?function\s+(?:estimate|count)Tokens\s*[(<]", re.M),  # TS
)

_SKIP = ("__pycache__", "/build/", "/node_modules/", "/target/", "/.venv/")
_EXTS = (".py", ".go", ".rs", ".ts")


def _scanned(p: Path) -> bool:
    s = p.as_posix()
    if any(part in s for part in _SKIP):
        return False
    if p.suffix not in _EXTS:
        return False
    # Tests may define a stub estimator; the rule is about production paths.
    return "/tests/" not in s and not p.name.startswith("test_") and not p.name.endswith("_test.go")


def find_estimators() -> dict[str, int]:
    """{repo-relative path: how many estimator definitions it holds}."""
    out: dict[str, int] = {}
    for root in (ROOT / "services", ROOT / "sdks"):
        for p in sorted(root.rglob("*")):
            if not p.is_file() or not _scanned(p):
                continue
            try:
                src = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            n = sum(len(pat.findall(src)) for pat in _PATTERNS)
            if n:
                out[p.relative_to(ROOT).as_posix()] = n
    return out


def check(found: dict[str, int]) -> list[str]:
    problems = []
    for path in sorted(set(found) - set(SANCTIONED)):
        problems.append(
            f"UNREGISTERED estimator: {path}\n"
            f"   A fifth token estimator is how 'one estimator' becomes four again. Either use\n"
            f"   `loreweave_context.estimate_tokens`, or add a row to SANCTIONED in\n"
            f"   {Path(__file__).name} saying why this one cannot be it."
        )
    for path in sorted(set(SANCTIONED) - set(found)):
        problems.append(
            f"STALE registry row: {path} no longer defines an estimator.\n"
            f"   Remove the row — a registry that only grows stops describing the repo."
        )
    for path, reason in sorted(SANCTIONED.items()):
        if not reason.strip():
            problems.append(f"EMPTY reason for {path} — the justification IS the row.")
    return problems


def self_test() -> int:
    """The check must FAIL on an unregistered estimator, and on a stale row."""
    fake = dict.fromkeys(SANCTIONED, 1)
    if check(fake):
        print("[estimator-ssot] SELFTEST FAIL — the true state does not pass")
        return 1
    if not check({**fake, "services/made-up/app/counter.py": 1}):
        print("[estimator-ssot] SELFTEST FAIL — an unregistered estimator passed")
        return 1
    dropped = dict(fake)
    dropped.pop(next(iter(dropped)))
    if not check(dropped):
        print("[estimator-ssot] SELFTEST FAIL — a stale registry row passed")
        return 1
    print("[estimator-ssot] SELFTEST PASS — a new estimator reds, and so does a stale row.")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    found = find_estimators()
    if "--list" in sys.argv:
        for path in sorted(found):
            mark = "ok " if path in SANCTIONED else "NEW"
            print(f"  [{mark}] {path}  ({found[path]} definition(s))")
        return 0
    problems = check(found)
    if problems:
        print("estimator-ssot-gate: FAIL")
        for p in problems:
            print("  " + p)
        return 1
    print(f"estimator-ssot-gate: PASS — {len(found)} token estimator(s), every one registered "
          f"with the reason it is not the kernel.")
    print("  The kernel is sdks/python/loreweave_context/tokens.py; translation delegates to "
          "it; knowledge is tiktoken (more accurate, not a copy); lore-enrichment + "
          "provider-registry are the BILLING convention, separate on purpose.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
