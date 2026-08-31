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

#: The deferral this gate's BASELINE *is* the mechanism for, named in code rather
#: than in a comment — `deferral-gate.py` counts a comment as prose, correctly, and
#: refused this the moment the old `KNOWN_RED` row was deleted. It is printed by
#: both arms that can wake the debt: a NEW offender (growth) and a STALE row (a
#: fingerprint outliving its code). So the id appears exactly when someone has to
#: act on it, which is the difference between a mechanism and a mention.
DEFERRAL = "D-GATE-ROT-LANGUAGE-BIAS"


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


def self_test() -> int:
    """Prove the detectors red, the twins stay clean, and the BASELINE shrinks.

    Three families, and the third is the one that had actually decayed.

    * **detectors** — every rule fires on its shape.
    * **twins** — and does not fire on the near-miss. This gate's own docstring
      says the ML-2 lookbehind is "what keeps the false-positive rate low", so
      `self.name.lower()` and `lvl.name.lower()` staying clean is a claim the
      gate makes about itself, checked here rather than trusted.
    * **baseline liveness** — a fingerprint whose code no longer exists is a
      standing exemption for a line nobody has written yet: reintroduce that
      statement at that path and it is waved through. A baseline's whole value
      is that it shrinks, and until this arm existed nothing watched whether it
      did. It found **seven** stale rows on its first run.
    """
    fails: list[str] = []
    arms = {"red": 0, "clean": 0}

    def want(label: str, rel: str, line: str, expect: list[str]) -> None:
        arms["red" if expect else "clean"] += 1
        got = scan_line(rel, line)
        if sorted(got) != sorted(expect):
            fails.append(f"scan_line({label}): got {got}, want {expect}")

    PY, TS = "services/x/app/a.py", "frontend/src/a.ts"

    # ── ML-5 ──────────────────────────────────────────────────────────────────
    want("dumps on a prose body", PY, "    s = json.dumps(body)", ["ml5-ensure-ascii"])
    want("the same with ensure_ascii=False", PY,
         "    s = json.dumps(body, ensure_ascii=False)", [])
    want("dumps encoded for the wire", PY,
         "    b = json.dumps(x).encode('utf-8')", ["ml5-ensure-ascii"])
    want("dumps of a non-body local", PY, "    s = json.dumps(counts)", [])
    # Language scoping: ML-5/ML-2 are Python-only rules, and a TS file must not
    # inherit them just because the text matches.
    want("the ML-5 shape in a .ts file", TS, "    s = json.dumps(body)", [])

    # ── ML-3 ──────────────────────────────────────────────────────────────────
    want("proper-noun regex", PY, '    RE = re.compile(r"[A-Z][a-z]+")', ["ml3-ascii-regex"])
    want("word-token regex", PY, '    RE = re.compile(r"\\b\\w+\\b")', ["ml3-word-token"])
    want("whitespace split", PY, "    parts = text.split(' ')", ["ml3-word-token"])
    want("ML-3 applies to TS too", TS, "    const p = text.split(' ')", ["ml3-word-token"])
    want("a script-aware regex", PY, '    RE = re.compile(r"\\p{L}+")', [])

    # ── ML-2, and the lookbehind that keeps it quiet ──────────────────────────
    want("bare name.lower()", PY, "    key = name.lower()", ["ml2-naive-normalize"])
    want("name.strip().lower()", PY, "    key = name.strip().lower()", ["ml2-naive-normalize"])
    want("an ATTRIBUTE access", PY, "    key = self.name.lower()", [])
    want("an ENUM access", PY, "    key = lvl.name.lower()", [])
    want("a bare .strip() with no fold", PY, "    key = name.strip()", [])

    # ── scope ─────────────────────────────────────────────────────────────────
    for rel, expect in (
        ("services/x/tests/test_a.py", True), ("services/x/app/fixtures/a.py", True),
        ("frontend/src/a.stories.tsx", True), ("frontend/src/a.spec.ts", True),
        ("services/x/app/a.py", False), ("frontend/src/pages/A.tsx", False),
    ):
        if is_test_file(rel) is not expect:
            fails.append(f"is_test_file({rel!r}) is not {expect}")

    # ── reach ─────────────────────────────────────────────────────────────────
    for d in SEARCH_DIRS:
        if not os.path.isdir(os.path.join(REPO_ROOT, *d.split("/"))):
            fails.append(
                f"PHANTOM SEARCH DIR: `{d}` is in SEARCH_DIRS and does not exist. The walk "
                f"skips a missing directory silently, so a rename retires this gate over "
                f"that tree with no change to its output.")
    found = collect(iter_full_scan())
    scanned = sum(1 for _ in iter_full_scan())
    if scanned < 500:
        fails.append(
            f"the walk reached only {scanned} scannable file(s) (floor 500). This gate is "
            f"not pointed at the runtime tree it claims to guard.")

    # ── baseline liveness: the arm that found seven ───────────────────────────
    live = {fingerprint(r, rel, ln) for r, _, rel, ln in found}
    stale = sorted(set(BASELINE) - live)
    if stale:
        fails.append(
            f"{len(stale)} BASELINE row(s) match nothing in the tree. A fingerprint whose "
            f"code is gone is a standing exemption for a line nobody has written yet — "
            f"rewrite that exact statement at that exact path and this gate waves it "
            f"through, and {DEFERRAL}'s baseline has stopped shrinking. Delete the row(s):"
            f"\n      " + "\n      ".join(s[:150] for s in stale))
    if not BASELINE:
        fails.append("BASELINE is empty; the staleness arm above would agree with anything")

    for f in fails:
        print(f"FAIL: {f}", file=sys.stderr)
    if fails:
        return 1
    print(f"language-bias-gate: self-test OK — {arms['red']} arm(s) go RED, {arms['clean']} "
          f"stay clean on the near-miss twin; walk reaches {scanned} file(s); all "
          f"{len(BASELINE)} baseline row(s) still name live code.")
    return 0


def main() -> int:
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(USAGE)
        return 0

    if "--self-test" in args:
        return self_test()

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
    print(f"Growth here is what wakes {DEFERRAL}: the baseline is that deferral's mechanism,")
    print("and it is only a mechanism while it can only shrink.")
    return 1


# Seeded from the current repo (2026-07-04). Re-generate with --update-baseline.
# 38 known offenders from the enterprise-hardening audit (Area 7). Each is a
# line-number-independent `rule|relpath|normalized-code` fingerprint, so the
# gate passes today and fails only on a NEW occurrence.
BASELINE = {
    # ── 2026-07-30 convergence run (the gate had been RED, so a new violation could
    # hide in the noise — one of the 19 offenders swept turned out to be a line I had
    # written myself hours earlier). These three are the residue: two hashes and one
    # non-prose fold. Each is a FALSE POSITIVE ON INTENT, kept visible rather than
    # silenced with an inline pragma.
    #
    # A fingerprint over ids/versions/ints. `ensure_ascii` changes the BYTES of the
    # digest and nothing about its correctness, so flipping it would invalidate every
    # stored `outline_fingerprint`/`bindings_fingerprint` — a re-run for every arc — in
    # exchange for nothing. There is no prose in the material.
    'ml5-ensure-ascii|services/composition-service/app/engine/arc_conformance_orchestrate.py|json.dumps(material, sort_keys=True, default=str).encode("utf-8")',
    # Same shape: a digest over a tool payload, used for cache identity. ALSO the
    # concurrent session's single most active file this session — the atom-edit drift
    # log records assuming a backend file was uncontested and being wrong twice, so it
    # is not touched here. See D-LANGBIAS-STREAM-TOOL-HASH.
    'ml5-ensure-ascii|services/chat-service/app/services/stream_service.py|json.dumps(tool_payload, sort_keys=True, default=str).encode()',
    # `_is_read_tool(name)` folds an MCP TOOL NAME (`composition_motif_get`) — an ASCII
    # identifier from our own registry, never user prose. The spine would be correct and
    # pointless here.
    'ml2-naive-normalize|services/chat-service/app/services/tool_surface.py|n = name.lower()',
    'ml2-naive-normalize|services/chat-service/app/client/known_entities_client.py|toks.add(name.strip().lower())',
    'ml2-naive-normalize|services/chat-service/app/services/steering.py|if name.casefold() in mentioned:',
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
    "ml3-word-token|frontend/src/pages/book-tabs/TranslateModal.tsx|<span className={cn('h-1.5 w-1.5 rounded-full', STATUS_BADGE[s.status].split(' ')[0])} />",
    'ml5-ensure-ascii|services/chat-service/app/events/voice_events.py|"payload": json.dumps(payload),',
    'ml5-ensure-ascii|services/chat-service/app/routers/feedback.py|message_id, json.dumps(payload),',
    'ml5-ensure-ascii|services/chat-service/app/routers/internal.py|json.dumps(body.working_memory_seed) if body.working_memory_seed is not None else None,',
    'ml5-ensure-ascii|services/chat-service/app/routers/sessions.py|gp_patch = json.dumps(body.generation_params.model_dump(exclude_unset=True))',
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
    'ml5-ensure-ascii|services/worker-ai/app/outbox_emit.py|json.dumps(payload, default=str),',
}
# PRUNED 2026-08-10 — seven rows whose subject no longer exists. Four ML-2 offenders
# were genuinely fixed (`worker-ai/runner.py` now imports the shared
# `normalize_entity_name` spine; the two `canon_check.py` folds and compaction's
# `term.lower()` are gone) and two ML-5 rows gained `ensure_ascii=False`;
# `sessions.py`'s `gp = ...` line was removed, its `gp_patch` sibling remains.
#
# They were found by the staleness arm of `--self-test`, added in the same change,
# and NOT by anything that existed before — which is the point. A baseline row whose
# code is gone is a **standing exemption for a line nobody wrote yet**: reintroduce
# that exact statement at that exact path and the gate waves it through, silently,
# because the fingerprint still matches. The whole value of a baseline is that it
# shrinks, and nothing was watching whether this one did.
#
# `D-LANGBIAS-COMPACTION-LOWER` and `D-LANGBIAS-CANONCHECK-LOWER` are discharged by
# the same finding; their explanatory comments went with their rows.
#
# ─────────────────────────────────────────────────────────────────────────────
# WHAT THE REMAINING ROWS ARE — `D-GATE-ROT-LANGUAGE-BIAS`, moved here 2026-08-10
# from a `KNOWN_RED` row in `gate-wiring-gate.py`, because THIS is where its
# subject lives. It is a CLASSIFICATION, not a list, so the next pass starts from
# analysis; two of the four classes change bytes that are already persisted, which
# is why none of them is a one-line edit.
#
#   (1) `json.dumps` -> a DB column  ·  DONE 2026-07-30, and it was not cosmetic.
#       `internal.py:76` was a SECURITY fix: that dump feeds `screen()` from
#       loreweave_safety, which NFKC-folds its input specifically so "unicode
#       look-alikes and width variants don't slip" (floor.py:120). With
#       `ensure_ascii=True` those characters became backslash-u escapes BEFORE the
#       fold ran, so a full-width payload in `working_memory_seed` walked past the
#       safety floor. **The serializer was defeating the screener** — found by
#       /review-impl asking whether an upstream step defeats a downstream defence.
#   (2) `json.dumps(...).encode()` -> a DIGEST  ·  x2 (`stream_service.py`,
#       `arc_conformance_orchestrate.py`). Flipping it changes EVERY hash, so it is
#       a cache/dedup invalidation decision, not an edit.
#   (3) `casefold()` as a PERSISTED IDENTITY KEY  ·  x5 (plan_forge x3, world_plan,
#       operations). Wants NFC/NFKC first — and normalising changes lookups against
#       rows ALREADY keyed the old way, so it needs a backfill plan or it orphans
#       them.
#   (4) `re.findall(r"\w{4,}")`  ·  x2 (`propose.py`). Space-delimited tokenizing,
#       which cannot work for CJK at all — a design choice, not a fix.
#   Plus ONE FALSE POSITIVE: `tool_surface.py` lowercases an MCP tool NAME, ASCII by
#   contract (closed-set snake_case), where `casefold()` is identical.
#
# WHY THE DEBT NO LONGER NEEDS THE GATE TO BE RED. `multilingual.md` sealed
# "deliberately RED, because baselining them would hide the debt". That was true of
# a baseline nothing audited. Measured the day the row was deleted: **all ten were
# already baselined anyway**, and the gate was red because of two UNRELATED lines
# added 2026-08-01 — so the register was being satisfied by the wrong offenders,
# which reads exactly like the debt still being tracked. This baseline now fails on
# growth AND on a row whose code no longer exists, which is strictly more mechanism
# than one row asserting redness. **Reversal trigger:** remove either arm and the
# original objection is valid again.


if __name__ == "__main__":
    sys.exit(main())
