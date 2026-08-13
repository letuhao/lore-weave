#!/usr/bin/env python3
"""authored-catalog-reader-gate — T38's checklist, which T38 did not have.

WHY THIS EXISTS, and it is a correction rather than a new idea. The plan claimed:

    "scripts/knowledge-access-gate.py + knowledge-http-surface-gate.py already enforce the
     allowlist T38 shrinks — the allowlist IS T38's checklist and can only shrink"

Measured 2026-08-11, that is false. `knowledge-access-gate`'s allowlist holds ONE entry (an
enrichment maintenance script). `knowledge-http-surface-gate`'s allowlist is EMPTY, and its own
pattern comment says:

    "The authored entities-LIST endpoint is intentionally NOT here (authored catalog, see header)"

T38 **is** "migrate the authored-catalog readers". Both gates therefore exclude precisely T38's
scope, by design and correctly — they enforce INV-KAL's *bi-temporal* half, which genuinely is
migrated. The error was the sentence that borrowed their green for a scope they never covered.
Both pass at HEAD, and both would pass with T38 entirely undone: a check that cannot fail is a
claim in the costume of evidence. See `D-T38-MECHANISM-IS-VACUOUS` in the plan.

── WHAT THIS GATE MEASURES ──────────────────────────────────────────────────────────────────

The AUTHORED CATALOG is `glossary_entities` (name / kind / short_description) served by
glossary-service over `/internal/books/{book}/entities`. Today consumers may read it directly —
both existing gates exempt it deliberately. **T38 is the task that changes that**, moving those
readers onto the KAL (`KalClient.roster`, which thins the list to id+name), and T47 records the
consequence: *"INV-KAL scope now covers writes + the authored catalog"*.

So this gate encodes the POST-T38 scope while T38 is still open: it pins today's reader set and
refuses to let it grow. The pinned list IS the migration checklist, the same shape as
`alive-column-deprecation-gate`, `derived-entity-id-gate` and `graph-port-gate`.

── WHY A NAME-GREP WOULD NOT HAVE WORKED, on either half ─────────────────────────────────────

**The table half is not detectable this way, and pretending otherwise would be worse than
skipping it.** `knowledge-access-gate` can grep `entity_attribute_values` because nothing else
is called that. `glossary_entities` is *also an obvious variable name*: measured across
services/, the majority of matches are Python identifiers, function names and prose —
`project_glossary_entities_to_nodes(...)`, a `glossary_entities: list[str]` parameter, a comment
listing context sections. knowledge-service reaches the catalog through `GlossaryClient` over
HTTP, not through the table. A gate flagging those would be ~all false positives, would be
silenced within a week, and would then be worth less than no gate. The HTTP half below is
precise, so the HTTP half is what is enforced.

**Comments and docstrings are stripped per language before matching**, for the same reason
`derived-entity-id-gate` strips them: that gate's baseline started at ELEVEN and the first run
corrected it to FIVE, because six files only MENTIONED the symbol. The identical trap is live
here — `worker-ai/app/clients.py` names the LIST endpoint twice in docstrings above the two
places it actually calls it, and translation-service's client documents three endpoints in
`Calls:` lines. Sizing T38 off a raw grep would over-state it and hide the real remainder
inside noise.

── SCOPE: READS, not writes ─────────────────────────────────────────────────────────────────

INV-KAL is a READ invariant, and KAL `roster`/`by-ids` are the sanctioned replacements, so the
three read shapes below are unambiguous. The authored-catalog WRITE surface (`/enrichments`,
`/canonical`, `/fold-snapshot`, and the bulk DELETE) shares URL prefixes but has no KAL
equivalent to migrate onto today; T47 says the scope grows to cover writes, and that is a
separate slice. Where a write shares a read's exact URL and cannot be told apart by path alone,
it is pinned with its reason rather than silently matched — see BASELINE.

    python scripts/authored-catalog-reader-gate.py            # gate (CI / pre-commit)
    python scripts/authored-catalog-reader-gate.py --print    # list findings, pin nothing

Exit 0 = the reader set is unchanged or smaller · 1 = it grew, or the baseline is stale.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_ROOT = os.path.join(ROOT, "services")

SCAN_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go")
EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv",
    "dist", "build", ".next", "coverage", ".mypy_cache", ".ruff_cache",
}

# The owners and the sanctioned federator. They ARE the endpoint / the KAL.
EXEMPT_SERVICE_PREFIXES = (
    os.path.join("glossary-service", ""),      # serves these routes
    os.path.join("knowledge-gateway", ""),     # the KAL — federates them on purpose
)

# ── the authored-catalog READ shapes ────────────────────────────────────────────────────────
# Ids are templated (f-string, ${...}, %s, fmt verbs), so each segment tolerates any run of
# non-slash/quote characters. The three shapes:
#   LIST          /internal/books/{book}/entities                (KAL `roster`)
#   BY-IDS        /internal/books/{book}/entities/by-ids         (KAL `roster` by id)
#   CANON-CONTENT /internal/books/{book}/entities/{id}/canon-content
# A path segment: either a templated expression or a run of plain characters. The braced
# alternative is not decoration — `f"…/entities/{ents[0]['entity_id']}/canon-content"` puts
# QUOTES inside the interpolation, and a segment defined as "no quotes" stops dead there.
# The first cut of this gate did exactly that and silently missed a real call site; the miss
# only surfaced because a hand grep had found it and the gate had not.
_SEG = r"(?:\$?\{[^{}]*\}|[^\s\"'`/])+"
_BOOKS = rf"/internal/books/{_SEG}/entities"
READ_RE = re.compile(
    rf"{_BOOKS}(?:"
    rf"/by-ids"                       # by-ids read
    rf"|/{_SEG}/canon-content"        # canon-content read
    rf"|(?=[\s\"'`?)]|$)"             # bare LIST — end of the URL, not a longer path
    r")"
)

# Suffixes owned by OTHER gates or by the write half. Matched first and skipped, so this gate
# never double-reports something `knowledge-http-surface-gate` already governs.
NOT_OURS = re.compile(
    r"/internal/books/[^\s\"'`]*/entities/[^\s\"'`]*"
    r"(?:facts|canonical-snapshot|timeline|attr-values|enrichments|fold-snapshot"
    r"|canonical|search)\b"
)

# ── the checklist ───────────────────────────────────────────────────────────────────────────
# Every consumer file that reads the authored catalog directly. Each entry must eventually move
# onto `KalClient.roster`; removing an entry is T38 progress. Paths are relative to services/.
#
# ⚠️ This baseline was produced BY the gate, and the gate corrected the hand-built version twice.
# A raw grep of the same pattern reported 21 hits across 8 files; comment/docstring stripping cut
# that to 10 real call sites. The dropped ones were `Calls: POST /internal/…` docstrings, module
# headers, and two comments naming the endpoint precisely BECAUSE they describe migrating off it.
#
# The two corrections are worth more than the count:
#   1. The hand list MISSED `eval_narrative_thread.py` — a nested-quote interpolation the first
#      regex could not cross (see `_SEG`). A grep found it and the gate did not, which is the
#      only reason it was caught.
#   2. The hand list wrongly EXEMPTED knowledge-service as an "owner". It owns the KG, not the
#      glossary; against the authored catalog it is a plain consumer, and it reads it by-ids.
#      Exempting a service because its name is nearby is how a gate acquires a blind spot.
BASELINE = {
    os.path.join("api-gateway-bff", "src", "assistant", "assistant.controller.ts"):
        "bulk DELETE on the LIST url — a WRITE the path alone cannot tell from a read; pinned "
        "so it stays visible, but NOT T38's to migrate (see the READS-not-writes scope note)",
    os.path.join("composition-service", "app", "clients", "glossary_client.py"):
        "by-ids read; this module's header already records its LIST read as moved to KalClient.roster",
    os.path.join("composition-service", "scripts", "eval_a_grounded.py"):
        "canon-content read from an eval script — not a runtime path, migrate last",
    os.path.join("composition-service", "scripts", "eval_narrative_thread.py"):
        "canon-content read from an eval script — not a runtime path, migrate last",
    os.path.join("knowledge-service", "app", "clients", "glossary_client.py"):
        "by-ids read (identity for the semantic selector) — knowledge-service owns the KG, "
        "NOT the glossary, so against the authored catalog it is a consumer like any other",
    os.path.join("translation-service", "app", "workers", "glossary_client.py"):
        "by-ids read",
}


def strip_py(text: str) -> str:
    """Blank `#` comments and triple-quoted strings, preserving line count."""
    text = re.sub(r'"""(?:.|\n)*?"""|\'\'\'(?:.|\n)*?\'\'\'',
                  lambda m: "\n" * m.group(0).count("\n"), text)
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "#":
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def strip_c_like(text: str) -> str:
    """Blank `//` and `/* */` comments in TS/JS/Go, preserving line count."""
    text = re.sub(r"/\*(?:.|\n)*?\*/",
                  lambda m: "\n" * m.group(0).count("\n"), text)
    return re.sub(r"//[^\n]*", "", text)


def scan(rel: str, raw: str) -> list[tuple[int, str]]:
    src = strip_py(raw) if rel.endswith(".py") else strip_c_like(raw)
    hits = []
    for n, line in enumerate(src.splitlines(), 1):
        if NOT_OURS.search(line):
            continue
        m = READ_RE.search(line)
        if m:
            hits.append((n, m.group(0)))
    return hits


def is_test(rel: str) -> bool:
    base = os.path.basename(rel)
    return (
        "/tests/" in rel.replace(os.sep, "/") or "/test/" in rel.replace(os.sep, "/")
        or "__mocks__" in rel or "fixtures" in rel
        or base.startswith("test_") or base.endswith("_test.go")
        or base.endswith((".spec.ts", ".spec.tsx", ".test.ts", ".test.tsx"))
    )


def collect() -> dict[str, list[tuple[int, str]]]:
    found: dict[str, list[tuple[int, str]]] = {}
    for base, subdirs, files in os.walk(SCAN_ROOT):
        subdirs[:] = [s for s in subdirs if s not in EXCLUDE_DIRS]
        for f in files:
            if not f.endswith(SCAN_EXTS):
                continue
            path = os.path.join(base, f)
            rel = os.path.relpath(path, SCAN_ROOT)
            if rel.startswith(EXEMPT_SERVICE_PREFIXES) or is_test(rel):
                continue
            try:
                raw = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            hits = scan(rel, raw)
            if hits:
                found[rel] = hits
    return found


def selftest() -> int:
    """Prove this gate can go red, on synthetic input, without touching the repo.

    Hand-biting in a terminal proves it to the person who ran it and to nobody else; CI cannot
    see a pasted transcript. `gate-teeth-gate` is right to count that as unproven — this gate
    shipped without it and grew that debt by one.

    The two cases are the ones the gate's accuracy actually rests on: it must SEE a call, and
    it must IGNORE prose that names the same endpoint. The second is not decoration — a
    docstring-blind version of this gate would have over-reported the baseline by 2x and hidden
    the real reader set inside noise.
    """
    ok = True

    call = 'url = f"{base}/internal/books/{book_id}/entities/by-ids"\n'
    if not scan("x.py", call):
        print("  FAIL — a real call site was not detected")
        ok = False

    prose = '"""Historically read /internal/books/{book_id}/entities directly."""\n'
    if scan("x.py", prose):
        print("  FAIL — a docstring mention was counted as a call site")
        ok = False

    # The nested-quote interpolation that the first version of `_SEG` could not cross. It cost
    # a real missed reader; it is pinned here so the regex cannot silently regress to it.
    nested = "_get(f\"/internal/books/{book}/entities/{ents[0]['entity_id']}/canon-content\")\n"
    if not scan("x.py", nested):
        print("  FAIL — a nested-quote interpolation was not detected")
        ok = False

    # A bi-temporal read belongs to knowledge-http-surface-gate; double-reporting it here would
    # make two gates argue about one finding.
    if scan("x.py", 'get(f"/internal/books/{b}/entities/{e}/facts")\n'):
        print("  FAIL — a bi-temporal read leaked into this gate's scope")
        ok = False

    print(f"[authored-catalog-reader-gate] SELFTEST {'PASS' if ok else 'FAIL'} — detects a call, "
          f"ignores a docstring, crosses a nested-quote interpolation, and leaves the "
          f"bi-temporal reads to their own gate (non-vacuous)")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", dest="just_print", action="store_true",
                    help="list findings without gating (used to build the baseline)")
    ap.add_argument("--selftest", action="store_true",
                    help="prove this gate can go red, on synthetic input")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if not os.path.isdir(SCAN_ROOT):
        print(f"[authored-catalog-reader-gate] SKIP — {SCAN_ROOT} not present")
        return 0

    found = collect()

    if args.just_print:
        total = sum(len(v) for v in found.values())
        print(f"[authored-catalog-reader-gate] {len(found)} file(s), {total} call site(s)\n")
        for rel in sorted(found):
            for n, frag in found[rel]:
                print(f"  {rel}:{n}  {frag}")
        return 0

    baseline = set(BASELINE)
    added, gone = sorted(set(found) - baseline), sorted(baseline - set(found))
    failed = False

    if added:
        failed = True
        print("[authored-catalog-reader-gate] FAIL — NEW direct reader(s) of the authored "
              "catalog:\n")
        for p in added:
            for n, frag in found[p]:
                print(f"  {p}:{n}  {frag}")
        print("\n  T38 migrates these onto the KAL — read the catalog through")
        print("  `KalClient.roster` (KNOWLEDGE_GATEWAY_URL /v1/kal/...), not glossary-service's")
        print("  `/internal/books/{book}/entities` directly. If this read genuinely must land")
        print("  first, add the file to BASELINE with a reason — that is a tracked debt, not a")
        print("  silent one.")

    if gone:
        failed = True
        print("[authored-catalog-reader-gate] FAIL — baseline names file(s) that no longer "
              "read the authored catalog directly:\n")
        for p in gone:
            print(f"  {p}   ({BASELINE[p]})")
        print("\n  Remove them from BASELINE — that IS T38 progress, and recording it is the")
        print("  point of the list. A stale baseline also leaves a slot a future reader can")
        print("  occupy without this gate noticing.")

    if not failed:
        total = sum(len(v) for v in found.values())
        print(f"[authored-catalog-reader-gate] PASS — {len(found)} file(s) / {total} call "
              f"site(s) read the authored catalog directly, exactly the pinned set; "
              f"the baseline can only shrink (T38's checklist)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
