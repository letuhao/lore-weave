#!/usr/bin/env python3
"""S1 · the generation-guard gate — enumerate PATHS, not modules, and reach every language.

Reads `contracts/generation-paths.yaml` and reds on four things:

  1. a PHANTOM row — its file or its symbol does not exist. The S12 lesson, three times over:
     that gate went green on its own motivating example because a doc comment mentioned the
     crate name, because a workspace list mentioned it, and finally because the gate's own
     docstring mentioned it. A registry nobody checks against the code is a document.
  2. a row claiming `guarded` whose `coverage_field` does not appear in its file. "It is
     guarded" is a claim; the field being emitted is the evidence.
  3. an `unguarded` row with no `owner`. An honest gap must be TRACKED. Untracked, it is
     indistinguishable from a gap nobody has noticed.
  4. the number of model-gateway callers NOT classified here GROWING past the recorded
     baseline. This is deliberately weak: the registry does not claim to cover all 94, and
     pretending otherwise is the "denominator from what I happened to look at" mistake. What it
     does guarantee is that the uncovered surface cannot silently expand.

Run:  python scripts/generation-guard-gate.py [--verbose]
Exit: 0 clean · 1 a finding.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "generation-paths.yaml"

#: How a model-gateway call looks in each language. Deliberately generous — a false candidate
#: costs a line in the "unclassified" count, a missed one costs a blind spot, and only the
#: second kind of error is dangerous here.
_CALLERS = {
    "python": (("services/*/app",), ("*.py",),
               re.compile(r"submit_and_wait|generate_text|chat_completion")),
    "go": (("services/*/internal", "services/*/cmd"), ("*.go",),
           re.compile(r"aiGateway|AIGateway|llmClient|LLMClient|ai_gateway")),
    "rust": (("services/*/src",), ("*.rs",), re.compile(r"\bllm\b|\bLlm|\bLLM")),
    "typescript": (("services/*/src",), ("*.ts",),
                   re.compile(r"aiGateway|callTool|providerRegistry")),
}

#: A symbol DEFINITION, per language. Matching a bare mention would let a comment satisfy the
#: gate — which is exactly how the S12 gate greened on its own docstring.
_DEFS = {
    "python": lambda s: re.compile(rf"^\s*(async\s+def|def|class)\s+{re.escape(s)}\b", re.M),
    "go": lambda s: re.compile(rf"^\s*func\s+(\([^)]*\)\s*)?{re.escape(s)}\b", re.M),
    "rust": lambda s: re.compile(
        rf"^\s*(pub\s+)?(async\s+)?(fn|struct|enum)\s+{re.escape(s)}\b", re.M),
    "typescript": lambda s: re.compile(
        rf"^\s*(export\s+)?(async\s+)?(function|class|const)\s+{re.escape(s)}\b", re.M),
}


def _load() -> dict:
    try:
        import yaml
    except ImportError:  # pragma: no cover
        print("generation-guard-gate: PyYAML is required", file=sys.stderr)
        raise SystemExit(2)
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


def _candidates(lang: str) -> set[pathlib.Path]:
    roots, globs, pattern = _CALLERS[lang]
    out: set[pathlib.Path] = set()
    for root_glob in roots:
        for base in ROOT.glob(root_glob):
            for g in globs:
                for f in base.rglob(g):
                    try:
                        if pattern.search(f.read_text(encoding="utf-8", errors="ignore")):
                            out.add(f)
                    except OSError:
                        continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    spec = _load()
    rows = spec.get("paths") or []
    findings: list[str] = []
    guarded = unguarded = 0
    registered: set[pathlib.Path] = set()

    for row in rows:
        rid = row.get("id", "<no id>")
        lang = row.get("language", "")
        path = ROOT / str(row.get("file", ""))
        if lang not in _DEFS:
            findings.append(f"{rid}: unknown language {lang!r}")
            continue
        if not path.is_file():
            findings.append(f"{rid}: PHANTOM — no such file {row.get('file')}")
            continue
        registered.add(path)
        body = path.read_text(encoding="utf-8", errors="ignore")
        symbol = str(row.get("symbol", ""))
        if not _DEFS[lang](symbol).search(body):
            findings.append(
                f"{rid}: PHANTOM — {symbol!r} is not DEFINED in {row.get('file')} "
                f"(a mention in a comment does not count)")
            continue

        status = row.get("status")
        if status == "guarded":
            guarded += 1
            field = str(row.get("coverage_field") or "")
            if not field:
                findings.append(f"{rid}: claims `guarded` with no coverage_field")
            elif field not in body:
                findings.append(
                    f"{rid}: claims `guarded` but {field!r} is never emitted in "
                    f"{row.get('file')} — the claim has no evidence")
        elif status == "unguarded":
            unguarded += 1
            if not row.get("owner"):
                findings.append(
                    f"{rid}: `unguarded` with no owner — an untracked gap is indistinguishable "
                    f"from one nobody noticed")
        else:
            findings.append(f"{rid}: unknown status {status!r}")

    # ── the code-derived denominator ─────────────────────────────────────────────────────
    baseline = (spec.get("discovery") or {}).get("baseline") or {}
    counts: dict[str, int] = {}
    for lang in _CALLERS:
        found = _candidates(lang)
        counts[lang] = len(found)
        want = baseline.get(lang)
        if want is None:
            findings.append(f"discovery: {lang} has no recorded baseline")
        elif len(found) > want:
            new = sorted(str(p.relative_to(ROOT)) for p in found - registered)[:8]
            findings.append(
                f"discovery: {lang} model-gateway callers grew {want} → {len(found)}. "
                f"Classify the new paths in contracts/generation-paths.yaml (or raise the "
                f"baseline with a note saying which). e.g. {new}")

    if args.verbose or findings:
        print(f"registry: {guarded} guarded · {unguarded} unguarded (tracked) · "
              f"{len(rows)} rows")
        print("model-gateway callers: " + " · ".join(f"{k}={v}" for k, v in counts.items()))

    if findings:
        print("\ngeneration-guard-gate: FAIL")
        for f in findings:
            print("  · " + f)
        return 1
    print(f"generation-guard-gate: PASS — {len(rows)} generation paths enumerated across "
          f"{len({r.get('language') for r in rows})} languages; "
          f"{guarded} guarded, {unguarded} tracked-unguarded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
