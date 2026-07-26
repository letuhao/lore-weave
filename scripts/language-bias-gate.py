#!/usr/bin/env python3
"""language-bias-gate.py — enforce LoreWeave's anti-language-bias standard.

Standard: docs/standards/multilingual.md (rules ML-2, ML-3, ML-5).
Modelled on scripts/ai-provider-gate.py: cross-platform pure-Python, an
embedded BASELINE so the gate PASSES on today's known offenders and only
FAILS on NEW ones (baseline seeded from the enterprise-hardening audit,
docs/plans/2026-07-04-enterprise-hardening-audit.md › Area 7).

Why this exists: the product is a multilingual novel platform, but
rule-based logic keeps getting written English-first and silently
degrades for zh/ja/ko/vi. This gate catches the three grep-detectable
shapes from multilingual.md:

  ML-5 · `json.dumps(<body>)` WITHOUT `ensure_ascii=False` on a
         request/message/event body carrying user prose (the `\\uXXXX`
         inflation tax on CJK — 2-3x wire/token bloat). Detected when the
         first positional arg is a body-ish name (body/event/payload/
         msg/message/envelope) OR the result is `.encode()`d for the wire.

  ML-3 · ASCII-shaped text regexes on prose paths: `[A-Z][a-z]` for
         proper-noun extraction (misses vi diacritics + ja kana + ko
         hangul), bare `\\b\\w+\\b` / `re.findall(r"\\w+")` / `.split(' ')`
         used to word-tokenize user text. The allowed forms are `\\p{L}`
         or explicit CJK ranges.

  ML-2 · Naive `.lower()`/`.casefold()` (optionally `.strip().lower()`)
         applied to a name/entity/title/query variable where the shared
         NFKC+casefold+CJK-fold spine belongs
         (sdks/python/loreweave_extraction/name_normalize.py). Heuristic,
         deliberately scoped to the normalization-KEY shape (bare
         identifier + .lower/.casefold) — bare `.strip()` whitespace
         guards are intentionally NOT flagged (they are not the defect and
         flood false positives).

Scope: services/** + frontend/src/** RUNTIME code. Tests, stories,
fixtures, `scripts/`, `eval/`, and `poc_*.py` are excluded (example model
names / ad-hoc analysis code are not the governed path).

Usage:
  python scripts/language-bias-gate.py             # full scan (CI / manual)
  python scripts/language-bias-gate.py --staged    # only git-staged files (pre-commit)
  python scripts/language-bias-gate.py --update-baseline   # re-seed BASELINE (maintainers)

Exit 0 = clean (or baseline-only). Exit 1 = a NEW violation.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SEARCH_DIRS = ("services", "frontend/src")
SCAN_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs")
EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv",
    "dist", "build", ".next", ".git", "vendor", "coverage",
    "storybook-static",
}

# ── detection patterns ────────────────────────────────────────────────

# ML-5 · a body carrying user prose serialized without ensure_ascii=False.
_ENSURE_ASCII_FALSE = re.compile(r"ensure_ascii\s*=\s*False")
# (a) first positional arg is a body-ish name.
ML5_BODY_ARG = re.compile(
    r"json\.dumps\(\s*(?:\*\*)?(body|event|payload|msg|message|envelope)\b"
)
# (b) the dump is encoded to bytes for a wire message.
ML5_WIRE_ENCODE = re.compile(r"json\.dumps\(.*\)\.encode\b")

# ML-3 · ASCII-shaped regexes / whitespace tokenizing on prose.
# Catches both `[A-Z][a-z]` and `[A-Z][\w` proper-noun heuristics — the latter
# (`[A-Z][\w'-]`, entity_detector) misses vi/ja/ko just like the former; a NEW
# occurrence must pair with a script-aware pass (app/extraction/scripts.py) or
# earn a baseline row.
ML3_PROPER_NOUN = re.compile(r"\[A-Z\]\[(?:a-z|\\w)")
ML3_WORD_TOKEN = re.compile(
    r"\\b\\w\+\\b"                                         # `\b\w+\b` literal
    r"|re\.findall\(\s*r?['\"]\\w"                         # re.findall(r"\w...")
    r"|\.split\(\s*['\"] ['\"]\s*\)"                       # .split(' ') / .split(" ")
    r"|\.split\(\s*/ /\s*\)"                               # JS .split(/ /)
)

# ML-2 · naive lower/casefold building a normalization key on a name var.
# Negative lookbehind on `.`/word-char keeps this to a BARE identifier, so
# enum access (`lvl.name.lower()`) and attribute forms (`self.name`) do NOT
# match — that is what keeps the false-positive rate low.
ML2_NAIVE_NORMALIZE = re.compile(
    r"(?<![.\w])"
    r"(?:name|entity|entity_name|canonical_name|title|query|surface|surface_form|term)"
    r"(?:\.strip\(\))?\.(?:lower|casefold)\(\)"
)

# (rule_id, human label) — grouping in the failure report.
RULE_LABELS = {
    "ml5-ensure-ascii": "ML-5 · json.dumps on a prose body without ensure_ascii=False",
    "ml3-ascii-regex": "ML-3 · ASCII-shaped proper-noun regex `[A-Z][a-z]` (fails vi/ja/ko)",
    "ml3-word-token": "ML-3 · whitespace/`\\w` word-tokenizing on user prose (use \\p{L}/CJK ranges)",
    "ml2-naive-normalize": "ML-2 · naive .lower()/.casefold() on a name/entity var (use the shared NFKC+CJK spine)",
}

PY_ONLY = {"ml5-ensure-ascii", "ml2-naive-normalize"}


def is_test_file(rel: str) -> bool:
    base = os.path.basename(rel)
    return (
        "/tests/" in rel
        or "/test/" in rel
        or "/.storybook/" in rel
        or "/fixtures/" in rel
        or "/__fixtures__/" in rel
        or "/__mocks__/" in rel
        or "/scripts/" in rel
        or "/eval/" in rel        # benchmark / eval harness scripts
        or "/benchmark/" in rel   # ad-hoc benchmark corpora loaders
        or rel.endswith("_test.go")
        or base.startswith(("test_", "poc_", "smoke_", "diag_", "calibrate_"))
        or base.endswith((
            ".spec.ts", ".spec.tsx", ".test.ts", ".test.tsx",
            ".stories.ts", ".stories.tsx",
        ))
        or base == "conftest.py"
    )


def fingerprint(rule: str, rel: str, line: str) -> str:
    """Line-number-independent identity: rule + path + normalized code.
    Robust to a line moving within a file; a genuinely new occurrence
    (new path or new code text) produces a new fingerprint → flagged."""
    return f"{rule}|{rel}|{' '.join(line.split())}"


def scan_line(rel: str, line: str) -> list[str]:
    """Return the rule-ids that fire on this line (language-scoped)."""
    is_py = rel.endswith(".py")
    hits: list[str] = []

    if is_py:
        if (ML5_BODY_ARG.search(line) or ML5_WIRE_ENCODE.search(line)) \
                and not _ENSURE_ASCII_FALSE.search(line):
            hits.append("ml5-ensure-ascii")
        if ML2_NAIVE_NORMALIZE.search(line):
            hits.append("ml2-naive-normalize")

    if ML3_PROPER_NOUN.search(line):
        hits.append("ml3-ascii-regex")
    if ML3_WORD_TOKEN.search(line):
        hits.append("ml3-word-token")
    return hits


def scan_file(path: str, rel: str) -> list[tuple[str, int, str, str]]:
    out: list[tuple[str, int, str, str]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for n, line in enumerate(fh, 1):
                for rule in scan_line(rel, line):
                    out.append((rule, n, rel, line.rstrip()))
    except OSError:
        pass
    return out


def iter_full_scan():
    for d in SEARCH_DIRS:
        root = os.path.join(REPO_ROOT, *d.split("/"))
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [x for x in dirnames if x not in EXCLUDE_DIRS]
            for fn in filenames:
                if fn.endswith(SCAN_EXTS):
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, REPO_ROOT).replace(os.sep, "/")
                    yield full, rel


def iter_staged():
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return
    prefixes = tuple(d + "/" for d in SEARCH_DIRS)
    for rel in res.stdout.splitlines():
        rel = rel.strip().replace(os.sep, "/")
        if not rel.endswith(SCAN_EXTS):
            continue
        if not rel.startswith(prefixes):
            continue
        if any(part in EXCLUDE_DIRS for part in rel.split("/")):
            continue
        full = os.path.join(REPO_ROOT, rel)
        if os.path.isfile(full):
            yield full, rel


def collect(files) -> list[tuple[str, int, str, str]]:
    out: list[tuple[str, int, str, str]] = []
    for full, rel in files:
        if is_test_file(rel):
            continue
        out.extend(scan_file(full, rel))
    return out


USAGE = """language-bias-gate.py — enforce docs/standards/multilingual.md (ML-2/ML-3/ML-5)

Flags NEW language-bias offenders in services/** + frontend/src/** runtime code
(json.dumps without ensure_ascii=False on prose bodies; `[A-Z][a-z]`/`\\w`/`.split(' ')`
prose tokenizing; naive .lower()/.casefold() on name/entity vars). An embedded
BASELINE lets the gate pass on today's known offenders and fail only on new ones.

Usage:
  python scripts/language-bias-gate.py               full scan (CI / manual)
  python scripts/language-bias-gate.py --staged      only git-staged files (pre-commit)
  python scripts/language-bias-gate.py --update-baseline   re-seed BASELINE (maintainers)
  python scripts/language-bias-gate.py --help        this message

Exit 0 = clean (or baseline-only). Exit 1 = a new violation."""


def main() -> int:
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(USAGE)
        return 0

    if "--update-baseline" in args:
        found = collect(iter_full_scan())
        fps = sorted({fingerprint(r, rel, ln) for r, _, rel, ln in found})
        print("BASELINE = {")
        for fp in fps:
            print(f"    {fp!r},")
        print("}")
        print(f"\n# {len(fps)} baselined offenders", file=sys.stderr)
        return 0

    staged = "--staged" in args
    files = iter_staged() if staged else iter_full_scan()
    found = collect(files)

    new = [v for v in found if fingerprint(v[0], v[2], v[3]) not in BASELINE]

    mode = "staged" if staged else "full"
    if not new:
        print(f"language-bias-gate ({mode}): OK — no new language-bias offenders "
              f"(baseline: {len(BASELINE)} known)")
        return 0

    print("language-bias-gate: FAIL — NEW language-bias offender(s)\n")
    print("Standard: docs/standards/multilingual.md (ML-2 / ML-3 / ML-5)\n")
    for rule in ("ml5-ensure-ascii", "ml3-ascii-regex", "ml3-word-token", "ml2-naive-normalize"):
        rule_hits = [v for v in new if v[0] == rule]
        if not rule_hits:
            continue
        print(f"[{RULE_LABELS[rule]}]")
        for _, n, rel, line in rule_hits:
            print(f"  {rel}:{n}: {line.strip()}")
        print()
    print("Fixes:")
    print("  ML-5 → add ensure_ascii=False to the json.dumps on the prose body.")
    print("  ML-3 → use \\p{L}/explicit CJK ranges or the CJK-aware chunkers, not `[A-Z][a-z]`/`\\w`.")
    print("  ML-2 → normalize via loreweave_extraction.name_normalize (NFKC+casefold+CJK), not bare .lower().")
    print("\nIf this is intentional/legacy, add a row to docs/deferred/DEFERRED.md and")
    print("re-seed the baseline (python scripts/language-bias-gate.py --update-baseline).")
    return 1


# Seeded from the current repo (2026-07-04). Re-generate with --update-baseline.
# 38 known offenders from the enterprise-hardening audit (Area 7). Each is a
# line-number-independent `rule|relpath|normalized-code` fingerprint, so the
# gate passes today and fails only on a NEW occurrence.
BASELINE = {
    'ml2-naive-normalize|services/chat-service/app/client/known_entities_client.py|toks.add(name.strip().lower())',
    # compaction.py `term.lower()` is a SYMMETRIC dedup key (used only as a `seen`-set
    # membership key; the unchanged `term` is what's stored) — low-risk (CJK is a lower()
    # no-op; Latin folds symmetrically), not name-normalization that corrupts output. Owned
    # by the context-budget track. Baselined so language-bias-gate can enforce as BLOCKING;
    # tracked in SESSION_HANDOFF for a casefold/name_normalize cleanup. See D-LANGBIAS-COMPACTION-LOWER.
    'ml2-naive-normalize|services/chat-service/app/services/compaction.py|k = term.lower()',
    'ml2-naive-normalize|services/chat-service/app/services/steering.py|if name.casefold() in mentioned:',
    'ml2-naive-normalize|services/composition-service/app/engine/canon_check.py|idx = low.find(name.lower())',
    'ml2-naive-normalize|services/composition-service/app/engine/cast_plan.py|key = name.strip().casefold()',
    'ml2-naive-normalize|services/composition-service/app/engine/character_plan.py|canon = folded.get(name.strip().casefold())',
    'ml2-naive-normalize|services/composition-service/app/engine/plan_forge/eval_fidelity.py|bad = any(b in name.lower() for b in blocked) if name else True',
    'ml2-naive-normalize|services/composition-service/app/engine/plan_forge/spec_index.py|q = query.lower()',
    'ml2-naive-normalize|services/composition-service/app/engine/plan_forge/spec_index.py|title.lower(),',
    'ml2-naive-normalize|services/knowledge-service/app/context/intent/abstract_query.py|if entity.lower() in msg_lower:',
    'ml2-naive-normalize|services/knowledge-service/app/context/selectors/absence.py|key = name.lower()',
    'ml2-naive-normalize|services/knowledge-service/app/context/selectors/absence.py|needle = entity.lower()',
    'ml2-naive-normalize|services/knowledge-service/app/extraction/entity_detector.py|return name.strip().casefold()',
    'ml2-naive-normalize|services/knowledge-service/app/extraction/pattern_writer.py|return name.strip().casefold()',
    'ml2-naive-normalize|services/knowledge-service/app/routers/public/graph_views.py|for ch in name.strip().lower():',
    'ml2-naive-normalize|services/translation-service/app/workers/extraction_worker.py|key = (str(ent.get("kind_code", "")), name.lower())',
    'ml2-naive-normalize|services/worker-ai/app/runner.py|n = name.lower()',
    # entity_detector's ENGLISH capitalized-phrase pass — intentionally kept and
    # now PAIRED with a Vietnamese-aware Latin regex + a CJK-family run pass
    # (Pass A4, app/extraction/scripts.py). It is not English-ONLY bias, so it is
    # baselined rather than "fixed". (glossary.py's old `[A-Z][a-z]+` was replaced
    # by LATIN_NAME_RE, so its former baseline row is gone.)
    'ml3-ascii-regex|services/knowledge-service/app/extraction/entity_detector.py|_CAPITALIZED_PHRASE_RE = re.compile(r"\\b[A-Z][\\w\'-]*(?:\\s+[A-Z][\\w\'-]*)*\\b")',
    'ml3-ascii-regex|services/knowledge-service/app/extraction/entity_detector.py|r"\\b([A-Z][\\w\'-]*(?:\\s+[A-Z][\\w\'-]*)*)\\s+"',
    # triple_extractor SVO subject regex is the ENGLISH pass, now PAIRED with a
    # per-language relation-marker extractor (relations.py: zh/vi SVO + ja/ko SOV,
    # D-ML-TRIPLE-SVO-SCRIPT DONE). English keeps this regex; non-English routes to
    # the marker path — so it's not English-ONLY bias, baselined not "fixed".
    'ml3-ascii-regex|services/knowledge-service/app/extraction/triple_extractor.py|_SUBJ = r"(?P<subj>[A-Z][\\w\'-]*(?:\\s+[A-Z][\\w\'-]*)*)"',
    # canon_check.py (D-KG-EXTRACTION-CANON-GATE POC track) — SYMMETRIC search-key
    # lower() (both haystack + needle lowered for a substring find; the unchanged
    # text is what's used), the same low-risk shape as the compaction.py entry
    # below. Owned by that track for a name_normalize cleanup. See D-LANGBIAS-CANONCHECK-LOWER.
    'ml2-naive-normalize|services/knowledge-service/app/extraction/canon_check.py|idx = text.lower().find(name.lower())',
    "ml3-word-token|frontend/src/pages/book-tabs/TranslateModal.tsx|<span className={cn('h-1.5 w-1.5 rounded-full', STATUS_BADGE[s.status].split(' ')[0])} />",
    'ml5-ensure-ascii|services/chat-service/app/events/voice_events.py|"payload": json.dumps(payload),',
    'ml5-ensure-ascii|services/chat-service/app/routers/feedback.py|message_id, json.dumps(payload),',
    'ml5-ensure-ascii|services/chat-service/app/routers/internal.py|json.dumps(body.working_memory_seed) if body.working_memory_seed is not None else None,',
    'ml5-ensure-ascii|services/chat-service/app/routers/sessions.py|gp = json.dumps(body.generation_params.model_dump(exclude_unset=True)) if body.generation_params else "{}"',
    'ml5-ensure-ascii|services/chat-service/app/routers/sessions.py|gp_patch = json.dumps(body.generation_params.model_dump(exclude_unset=True))',
    'ml5-ensure-ascii|services/composition-service/app/db/repositories/outbox.py|aggregate_id, event_type, json.dumps(payload or {}, default=str),',
    'ml5-ensure-ascii|services/jobs-service/app/projection/consumer.py|stream, msg_id, json.dumps(payload) if payload is not None else None, str(exc),',
    'ml5-ensure-ascii|services/knowledge-service/app/context/cache_invalidation.py|json.dumps(payload),',
    'ml5-ensure-ascii|services/knowledge-service/app/db/repositories/extraction_jobs.py|json.dumps(payload, separators=(",", ":")).encode("utf-8"),',
    'ml5-ensure-ascii|services/knowledge-service/app/db/repositories/triage.py|json.dumps(payload),',
    'ml5-ensure-ascii|services/knowledge-service/app/events/consumer.py|json.dumps(payload), str(exc)[:2000], self.max_retries,',
    'ml5-ensure-ascii|services/knowledge-service/app/events/outbox_emit.py|json.dumps(payload, default=str),',
    'ml5-ensure-ascii|services/knowledge-service/app/ontology/confirm.py|payload = json.dumps(claims._payload(), separators=(",", ":"), sort_keys=True).encode("utf-8")',
    'ml5-ensure-ascii|services/learning-service/app/events/consumer.py|json.dumps(payload), str(exc)[:2000], self.max_retries,',
    'ml5-ensure-ascii|services/learning-service/app/judges/decoupled_judge.py|aggregate_id, json.dumps(body),',
    'ml5-ensure-ascii|services/translation-service/app/routers/versions.py|hv_id, str(body.block_index), json.dumps(body.block),',
    'ml5-ensure-ascii|services/translation-service/app/routers/versions.py|json.dumps(body.translated_body_json) if body.translated_body_json is not None else None,',
    'ml5-ensure-ascii|services/translation-service/app/workers/chapter_worker.py|event_type, aggregate_type, aggregate_id, json.dumps(payload),',
    'ml5-ensure-ascii|services/worker-ai/app/outbox_emit.py|json.dumps(payload, default=str),',
}


if __name__ == "__main__":
    sys.exit(main())
