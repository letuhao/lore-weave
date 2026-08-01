#!/usr/bin/env python3
"""design-lint.py — Layer-1 mechanical lint for the LLM MMO RPG design corpus.

Cross-platform, Python 3.10+, stdlib only (same reasons as ai-provider-gate.py:
no bash, no /tmp, works on Windows).

WHY THIS EXISTS. The 2026-07-26 reconciliation audit
(docs/03_planning/LLM_MMO_RPG/19_reconciliation_register.md §14) found ~150
cross-doc defects with one root cause: "documents are locked individually;
correctness is a property of the set." This lint is the mechanical guard for
the cheapest-to-check cross-doc classes.

CHECKS (each independently toggleable via --check):

  symbol        unregistered-prefix — every stable-ID reference of the shape
                PREFIX-<letter?><number> (RLS-A12, EVT-L13, DP-Ch18, REC-54)
                must have its PREFIX declared in the id catalog
                (00_foundation/06_id_catalog.md, "Prefix" column).
  link          broken-link — every relative markdown link must resolve to an
                existing file (anchors ignored; external URLs skipped).
  registration  phantom-registration — a line claiming "(registered ...)" or
                "registered YYYY-MM-DD" for a prefix that does NOT appear in
                _boundaries/01_feature_ownership_matrix.md. (This exact defect
                shipped 4 times.)
  count         count-drift — a tight "N variants of `X`" claim is VERIFIED
                against the real Rust enum `X` in crates/ + services/. Precision
                over recall on purpose: the number and the symbol must be
                adjacent (see COUNT_FORMS), because a same-line matcher read
                "(the §11 variant" as a count and mis-attributed one symbol's
                number to another — and a lint that cries wolf gets switched
                off, which is how this check spent its first life as INFO-only.
                TWO SOURCES since 2026-07-30 (REC-98): the real Rust enum,
                and — when the enum is SPEC-ONLY — the declaration in the same
                document's own rust block. The second closed this check's own
                documented hole ("it can only check enums that EXIST in code"),
                which had let `EF_001` claim "4 variants V1" beside a 5-variant
                declaration in the same file. Per-file on purpose: three docs
                declare `pub enum ActorId` and two are legitimately different
                types (DP's vs the feature layer's), so a cross-doc comparison
                would false-positive on its first run.
                Guards, each bite-tested, and each added because running it
                found the case: elided bodies (`...`) are illustrative not
                declarations; commented-out enums must not phantom (MAP_001
                carries a struck-through `ChannelTier`); version-partitioned
                enums (`// V1` / `// V2+` in the body) have NO single arity and
                are excluded, detected BEFORE comment stripping since the
                markers live in the comments the stripper removes.
                Exempt a real false positive (a name collision, a historical
                claim) with `design-lint: ok count — reason` on the line or the
                one above, or in an HTML comment to scope it to the whole file.

ALLOWLIST (symbol check):
  - scripts/design-lint.allow.json — {"prefixes": {"UTF": "reason", ...}},
    corpus-wide (for non-namespace tokens like UTF-8 / ISO-8601 / GPT-4).
  - inline pragma in a doc, scoped to that doc only:
      <!-- design-lint: ok prefix XYZ — reason -->

USAGE:
  python scripts/design-lint.py                       # full corpus, all checks
  python scripts/design-lint.py --path <dir>          # another corpus root
  python scripts/design-lint.py --check symbol,link   # subset of checks
  python scripts/design-lint.py --max-print 0         # print every finding

EXIT: 0 = clean · 1 = findings · 2 = usage/config error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from collections import Counter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DEFAULT_CORPUS = os.path.join(REPO_ROOT, "docs", "03_planning", "LLM_MMO_RPG")
CATALOG_REL = os.path.join("00_foundation", "06_id_catalog.md")
MATRIX_REL = os.path.join("_boundaries", "01_feature_ownership_matrix.md")
DEFAULT_ALLOWLIST = os.path.join(SCRIPT_DIR, "design-lint.allow.json")
ALL_CHECKS = ("symbol", "link", "registration", "count", "scale-band")
KIND_OF_CHECK = {
    "symbol": "unregistered-prefix",
    "link": "broken-link",
    "registration": "phantom-registration",
    "count": "count-drift",
    "scale-band": "scale-band-drift",
}
GEO_REL = os.path.join("features", "00_geography", "GEO_001_world_geometry.md")
WORLD_SCALE_RS = os.path.join(REPO_ROOT, "crates", "world-gen", "src", "creative_seed.rs")

# ── patterns ──────────────────────────────────────────────────────────────
# Stable-ID reference. Letter slot is any single capital or "Ch" — a superset
# of the originally spec'd A|D|Q|R|F|I|L|P|T|V|G|Ch, because DP-K7, EVT-S3 and
# ITM-C13 are real references the narrow set would miss.
ID_REF = re.compile(r"\b([A-Z]{2,5})-(?:Ch|[A-Z])?\d+[a-z]?\b")
# A prefix token as it appears in the catalog's "Prefix" column or on a
# registration-claim line: capitals followed by '-', a digit, or '*'.
PREFIX_TOKEN = re.compile(r"\b([A-Z]{2,5})(?=[-\d*])")
PRAGMA = re.compile(r"design-lint:\s*ok\s+prefix\s+([A-Z]{2,6})")
# File-scoped opt-out for the count check (e.g. a file of verbatim third-party
# or model-generated claims, which is evidence rather than an assertion we make).
COUNT_PRAGMA = re.compile(r"design-lint:\s*ok\s+count\b")

# ── count-drift: "N variants of `X`" vs the actual Rust enum ───────────────
#
# THE BUG THIS EXISTS TO PREVENT. `ABL_001`'s `EffectOp` is called a "closed
# 9-variant vocabulary" in three places and an 11-variant one in a fourth. The
# disagreement is the point: nobody knew, and nothing checked (XST-F1). The
# same class had already produced `ModifierSource::ALL` listing 3 of 6 variants
# — see `scripts/closed-set-gate.py`, which is this check's code-side twin.
#
# PRECISION OVER RECALL, DELIBERATELY. The first version of this matched a
# number and a symbol anywhere on the SAME LINE, and ~8 of its 11 "findings"
# were its own parse errors: `(the §11 variant` read as "11 variants", and
# "`ZoneType` (6 variants) | `ZoneRole` (4 …)" attributed ZoneType's count to
# ZoneRole. A lint that cries wolf gets switched off — which is exactly how
# this check spent its first life as INFO-only. So the number and the symbol
# must be ADJACENT, in one of four recognised shapes, and everything looser is
# left uncounted on purpose.
#
# KNOWN LIMIT: it can only check enums that EXIST in code. `EffectOp` is
# spec-only, which is precisely why nobody could settle 9 vs 11 — this check
# will start covering it the day ABL_001 is implemented, and not before.
COUNT_FORMS = (
    (re.compile(r"`([A-Za-z_]\w*)`\s*\(\s*(\d+)[\s-]*variants?\b", re.I), 1, 2),
    (re.compile(r"(\d+)[\s-]*variant\s+`([A-Za-z_]\w*)`", re.I), 2, 1),
    (re.compile(r"`([A-Za-z_]\w*)`\s*(?:—|-|:)\s*(\d+)[\s-]*variants?\b", re.I), 1, 2),
    (re.compile(r"`([A-Za-z_]\w*)`\s+(\d+)[\s-]*variant\b", re.I), 1, 2),
)


# ── the LOOSE form, safe ONLY because it is file-scoped ─────────────────────
#
# WHY A LOOSE MATCHER IS ALLOWED HERE WHEN IT WAS BANNED ABOVE. `COUNT_FORMS`
# requires the number and the symbol to be ADJACENT, because a same-line matcher
# produced ~8 parse errors in 11 findings ("(the §11 variant" read as a count).
# That trade is right for a corpus-wide check. But it MISSES the defect this
# source exists for: `EF_001:67` reads
#
#     | **EntityId** | Closed sum type — `Pc(PcId) \| …` | 4 variants V1. …
#
# — bold rather than backticked, and the count is a table cell away. Adjacency
# never fires, so the "4 variants" claim sat beside a FIVE-variant declaration in
# the same file (REC-98).
#
# The narrowing that makes loose matching safe is that the symbol must name an
# enum THIS FILE DECLARES. The original false-positive mode cannot survive it:
# "§11 variant" names no enum, so there is nothing to compare against. And the
# mis-attribution mode — "`ZoneType` (6 variants) | `ZoneRole` (4 …)" giving one
# symbol's number to another — is killed by requiring EXACTLY ONE declared enum
# name on the line. Two candidates means the line is ambiguous, so it is skipped
# rather than guessed. Both are bite-tested.
LOOSE_SYMBOL = re.compile(r"(?:`|\*\*)([A-Za-z_]\w*)(?:`|\*\*)")
LOOSE_COUNT = re.compile(r"\b(\d+)[\s-]*variants?\b", re.I)


def loose_count_claim(line: str, declared: dict):
    """(symbol, claimed) when the line names EXACTLY ONE file-declared enum and
    exactly one variant count. Returns None on any ambiguity — skipping is the
    correct answer for a check whose first life ended in false positives."""
    if not declared:
        return None
    names = {m for m in LOOSE_SYMBOL.findall(line) if m in declared}
    if len(names) != 1:
        return None
    counts = LOOSE_COUNT.findall(line)
    if len(counts) != 1:
        return None
    return names.pop(), int(counts[0])


def rust_enum_arities(roots=("crates", "services")) -> dict:
    """enum name -> {arity: [defining files]}. Parsed with the closed-set-gate
    parser so the two checks cannot disagree about what a variant is."""
    import importlib.util

    gate = os.path.join(SCRIPT_DIR, "closed-set-gate.py")
    if not os.path.exists(gate):
        return {}
    spec = importlib.util.spec_from_file_location("_closed_set_gate", gate)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    out: dict = {}
    for base in roots:
        base_dir = os.path.join(REPO_ROOT, base)
        for dirpath, dirnames, filenames in os.walk(base_dir):
            dirnames[:] = [d for d in dirnames if d not in
                           {"target", "node_modules", ".git", "dist", "build"}]
            for fn in filenames:
                if not fn.endswith(".rs"):
                    continue
                path = os.path.join(dirpath, fn)
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as fh:
                        src = fh.read()
                except OSError:
                    continue
                if "enum" not in src:
                    continue
                rel = os.path.relpath(path, REPO_ROOT).replace("\\", "/")
                for name, variants in mod.parse_enums(mod.strip_comments(src)).items():
                    out.setdefault(name, {}).setdefault(len(variants), []).append(rel)
    return out


# ── count-drift, second source: enums DECLARED IN THE CORPUS ITSELF ──────────
#
# THE BUG THIS CLOSES, and it is the check's own documented hole. `count` states:
# "KNOWN LIMIT: it can only check enums that EXIST in code." `EntityId` is
# spec-only — and on 2026-07-30 `EF_001` carried "4 variants V1" at line 67 next
# to a FIVE-variant `pub enum EntityId { …, Place(PlaceId) }` at line 352, in the
# SAME FILE, with nothing able to look. That was the THIRD half-applied amendment
# of one arc (after SPG-R1 and the "Applied so far" claim, REC-97), which is the
# point at which the answer stops being another careful sweep.
#
# PER-FILE, AND THAT IS A DESIGN DECISION, NOT A SHORTCUT. A cross-document
# version would have false-positived on its FIRST run: three docs declare
# `pub enum ActorId`, and two of them are legitimately different types —
# `06_data_plane/17_channel_lifecycle.md` declares the DATA PLANE's
# `{Player, Npc}` (2 variants) while `EF_001`/`NPC_001` declare the FEATURE
# layer's `{Pc, Npc, Synthetic, Admin, Locus}` (5). Both correct; it is the
# DP-A13 boundary. Per-file has no homonym problem because two files never meet,
# and it still catches the defect exactly. Cross-doc parity is deferred as
# `D-SPEC-CODE-ENUM-PARITY` rather than shipped noisy — a lint that cries wolf
# gets switched off, which is how this very check spent its first life INFO-only.
RUST_FENCE = re.compile(r"^\s*```+\s*rust\b", re.I)
FENCE_END = re.compile(r"^\s*```+\s*$")
# An elided body is ILLUSTRATIVE, not a declaration. Counting it would contradict
# a correct claim with a partial sample — bite-tested as a NON-finding.
ELISION = re.compile(r"\.\.\.|…")
# A VERSION-PARTITIONED enum has no single arity, so no claim about it can be
# checked against a total. Found by running the loose form over the corpus: it
# flagged `MemoryQuery` ("V1 4 variants; V2+ adds …" against a 6-variant block
# whose body is commented `// V1 query types` / `// V2+ additive`) and
# `SpatialPreference` the same way. BOTH CLAIMS ARE CORRECT — they scope
# themselves to V1 while the block declares the V1+V2 union. Comparing them to
# the total is the check misreading the corpus, not the corpus being wrong.
#
# Detected on the RAW body, BEFORE comment stripping, because the version markers
# live in exactly the comments the stripper removes. That ordering is the whole
# trick and is bite-tested.
VERSIONED_BODY = re.compile(r"//.*\bV\d\+?", re.I)


def corpus_enum_arities(lines) -> dict:
    """{enum name: arity} for enums declared in this FILE's rust code blocks.

    Parsed with `closed-set-gate`'s parser + comment stripper, the same pair
    `rust_enum_arities` uses, so the checks cannot disagree about what a variant
    is. The stripper is load-bearing here and not theoretical: `MAP_001` carries a
    deliberately COMMENTED-OUT `// pub enum ChannelTier { … }` recording a
    retirement, and a parser that counted it would invent a phantom enum out of
    documentation. Bite-tested against that real block.
    """
    import importlib.util

    gate = os.path.join(SCRIPT_DIR, "closed-set-gate.py")
    if not os.path.exists(gate):
        return {}
    spec = importlib.util.spec_from_file_location("_closed_set_gate", gate)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    out: dict[str, int] = {}
    block: list[str] = []
    inside = False
    for line in lines:
        if not inside:
            if RUST_FENCE.match(line):
                inside, block = True, []
            continue
        if FENCE_END.match(line):
            body = "\n".join(block)
            inside = False
            if ELISION.search(body):
                continue                      # illustrative, not a declaration
            if VERSIONED_BODY.search(body):
                continue                      # V1/V2+ partitioned: no single arity
            for name, variants in mod.parse_enums(mod.strip_comments(body)).items():
                # First declaration in the file wins; a file that declares one enum
                # twice is its own problem and not this check's to adjudicate.
                out.setdefault(name, len(variants))
            continue
        block.append(line)
    return out


def count_claim(line: str):
    """(symbol, claimed) for a tight adjacency form, else None."""
    for rx, sym_g, num_g in COUNT_FORMS:
        m = rx.search(line)
        if m:
            return m.group(sym_g), int(m.group(num_g))
    return None
MD_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
INLINE_CODE = re.compile(r"`[^`]*`")
FENCE = re.compile(r"^\s*(```|~~~)")
REG_CLAIM = re.compile(r"\(registered\b|\bregistered\s+(?:on\s+)?20\d\d-\d\d-\d\d", re.I)
COUNT_ASSERT = re.compile(
    r"\b\d+\s+(?:variants?|tools?|checks?|validators?|slots?|states?|events?"
    r"|shapes?|kinds?|types?|fields?|columns?|rows?|entries|items?|modes?"
    r"|phases?|tiers?|levels?|categories|namespaces?|prefixes?)\b"
    r"|\bcount\s*=\s*\d+",
    re.I,
)


def die(msg: str) -> "NoReturn":  # noqa: F821 — py3.10 has NoReturn in typing only
    print(f"design-lint: error: {msg}", file=sys.stderr)
    sys.exit(2)


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        return fh.read()


def load_allowlist(path: str, explicit: bool) -> dict[str, str]:
    """prefix → reason. A missing default file is fine; a missing --allowlist
    file is a config error."""
    if not os.path.isfile(path):
        if explicit:
            die(f"allowlist not found: {path}")
        return {}
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        die(f"allowlist is not valid JSON ({path}): {exc}")
    prefixes = data.get("prefixes", {})
    if isinstance(prefixes, list):  # tolerate the bare-list form
        return {p: "(no reason recorded)" for p in prefixes}
    if not isinstance(prefixes, dict):
        die(f'allowlist "prefixes" must be an object or list ({path})')
    return dict(prefixes)


def registered_prefixes(catalog_path: str) -> set[str]:
    """Prefixes declared in the id catalog. Only the FIRST column of table
    rows counts as a declaration — a prefix merely *mentioned* in a scope or
    example cell (e.g. "closes AUD-F5") does not register it."""
    prefixes: set[str] = set()
    for line in read_text(catalog_path).splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = line.split("|")
        if len(cells) < 3:
            continue
        first = cells[1]
        if set(first.strip()) <= {"-", ":", " "}:  # header separator row
            continue
        prefixes.update(PREFIX_TOKEN.findall(first))
    return prefixes


def iter_md_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            if fn.endswith(".md"):
                yield os.path.join(dirpath, fn)


def iter_staged_md_files(root: str):
    """Staged `.md` files under `root` — the pre-commit scope.

    Deleted/renamed-away paths are filtered by the isfile check, so a commit
    that removes a doc doesn't fail on its own absence.
    """
    import subprocess
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        die(f"--staged needs a working `git diff --cached`: {e}")
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    for rel in out.splitlines():
        if not rel.strip().endswith(".md"):
            continue
        path = os.path.abspath(os.path.join(repo_root, rel.strip()))
        if os.path.isfile(path) and (path + os.sep).startswith(root + os.sep):
            yield path


# ── per-file scanning ─────────────────────────────────────────────────────

def scan_file(path, rel, lines, checks, registered, allow, matrix_text, findings,
              counters, enum_arities=None, corpus_enums=None):
    corpus_enums = corpus_enums if corpus_enums is not None else {}
    pragma_ok = {m for line in lines for m in PRAGMA.findall(line)}
    # File-scoped only when the pragma sits in an HTML comment; otherwise it is
    # line-scoped, so muting one collision does not blind a whole document.
    count_muted = any(COUNT_PRAGMA.search(l) for l in lines if l.strip().startswith("<!--"))
    file_dir = os.path.dirname(path)
    in_fence = False
    # filename-derived fallback prefix for registration claims (COMB_003_… → COMB)
    m = re.match(r"([A-Z]{2,5})[_\d]", os.path.basename(path))
    file_prefix = m.group(1) if m else None

    for n, line in enumerate(lines, 1):
        if FENCE.match(line):
            in_fence = not in_fence

        if "symbol" in checks:
            seen_here: set[str] = set()
            for im in ID_REF.finditer(line):
                prefix, ref = im.group(1), im.group(0)
                if prefix in registered or prefix in allow or prefix in pragma_ok:
                    continue
                if ref in seen_here:
                    continue
                seen_here.add(ref)
                findings.append((rel, n, "unregistered-prefix",
                                 f"`{ref}` — prefix `{prefix}` not declared in the id catalog"))
                counters["symbol_prefixes"][prefix] += 1

        if "link" in checks and not in_fence:
            stripped = INLINE_CODE.sub("", line)
            for lm in MD_LINK.finditer(stripped):
                target = urllib.parse.unquote(lm.group(1)).strip("<>")
                target = target.split("#", 1)[0]
                if not target or "://" in target or target.startswith(("mailto:", "{")):
                    continue
                base = REPO_ROOT if target.startswith("/") else file_dir
                resolved = os.path.normpath(os.path.join(base, target.lstrip("/")))
                if not os.path.exists(resolved):
                    findings.append((rel, n, "broken-link",
                                     f"target does not exist: {lm.group(1)}"))

        if "registration" in checks:
            rm = REG_CLAIM.search(line)
            if rm:
                cands = [(t.start(), t.group(1)) for t in PREFIX_TOKEN.finditer(line)]
                before = [p for pos, p in cands if pos < rm.start()]
                named = (before[-1] if before
                         else (cands[0][1] if cands else file_prefix))
                if named and named not in allow and named not in pragma_ok:
                    if not re.search(rf"\b{re.escape(named)}\b", matrix_text):
                        findings.append((rel, n, "phantom-registration",
                                         f"claims registration for `{named}` but `{named}` does not "
                                         f"appear in the feature ownership matrix"))

        if "count" in checks:
            if COUNT_ASSERT.search(line):
                counters["count_assertions"] += 1
            line_muted = count_muted or COUNT_PRAGMA.search(line) or (
                n >= 2 and COUNT_PRAGMA.search(lines[n - 2]))
            claim = None if line_muted else count_claim(line)
            if claim is None and not line_muted:
                # Adjacency missed it; try the file-scoped loose form.
                claim = loose_count_claim(line, corpus_enums)
            if claim:
                sym, claimed = claim
                arities = (enum_arities or {}).get(sym)
                if arities:
                    counters["count_checked"] += 1
                    if claimed not in arities:
                        actual = sorted(arities)
                        where = arities[actual[0]][0]
                        findings.append((rel, n, "count-drift",
                                         f"claims `{sym}` has {claimed} variant(s); the enum in "
                                         f"`{where}` has {actual if len(actual) > 1 else actual[0]}"))
                elif sym in corpus_enums:
                    # SPEC-ONLY enum — the check's documented KNOWN LIMIT, closed
                    # 2026-07-30. Compared against the declaration IN THIS FILE, so
                    # there is no homonym ambiguity (see corpus_enum_arities).
                    counters["count_checked_corpus"] += 1
                    real = corpus_enums[sym]
                    if claimed != real:
                        findings.append((rel, n, "count-drift",
                                         f"claims `{sym}` has {claimed} variant(s), but THIS FILE "
                                         f"declares it with {real} — a document disagreeing with its "
                                         f"own code block is how a half-applied amendment hides "
                                         f"(REC-97/REC-98). The enum is spec-only, so nothing in "
                                         f"crates/ or services/ can arbitrate; fix whichever is stale"))


# ── scale-band: GEO_001's declared production scales vs the real generator ──
#
# THE BUG THIS EXISTS TO PREVENT, measured 2026-07-30. GEO_001 declared
# `WorldScale` as "closed 5 V1" with cell counts 1024 / 2048 / 8192 / 12288 /
# 16384. The shipped `crates/world-gen` had SIX variants and the real counts
# 1024 / 2025 / 8281 / 12321 / 16384 / 501264 — three numbers wrong and one
# variant missing. The sixth, `Gigaplanet` (501 264), VIOLATES the same doc's own
# `cell_count_out_of_bounds` band of [1024, 16384], and said so in its own Rust
# comment: "Gigaplanet deliberately exceeds it". Spec and generator disagreed for
# ~10 weeks and nothing looked.
#
# WHY THE `count` CHECK DID NOT CATCH IT. `count` needs the adjacency
# "`X` (N variants)"; the phrasing "closed 5 V1" walks past COUNT_FORMS. That is
# a deliberate precision trade there — so the guard for THIS class must not
# depend on phrasing at all.
#
# WHY IT IS NOT A UNIT TEST IN THE CRATE. `GEO_GENERATOR_PLAN` §1 makes the
# crate's independence explicit: "Decoupled from the LLM MMO RPG engine: no
# DP-kernel, no event sourcing, no aggregates, no foundation tier." A GEO_001
# band constant inside `world-gen` would break that — and would be near-vacuous
# besides, comparing a constant to a copy of itself. The defect is TWO DOCUMENTS
# DRIFTING APART, so the check must read both sides and cannot be satisfied by
# editing one.
SCALE_BLOCK = re.compile(
    r"<!--\s*geo-scale-band:begin.*?-->(?P<body>.*?)(?:<!--\s*geo-scale-band:end|\Z)",
    re.S)
BAND_RE = re.compile(r"^\s*cell_count_band:\s*\[\s*(\d+)\s*,\s*(\d+)\s*\]", re.M)
GRID_ARM = re.compile(r"WorldScale::(\w+)\s*=>\s*(\d+)")
# Trailing comma is OPTIONAL on purpose. Requiring it made the check FAIL OPEN:
# Rust permits a comma-less final match arm, so `WorldScale::Terraplanet => 900`
# would be absent from `counts` AND therefore absent from `unlisted` — invisible
# to the one check whose whole point is "a new variant is production-or-not by
# DECISION, never by default". Found by /review-impl, bite-tested below.


def world_scale_cell_counts(path: str = WORLD_SCALE_RS) -> dict[str, int]:
    """{variant: cell_count} from the generator's own `grid_side` arms.

    Count is `(g-2)^2 + 4*(g-1)`, the formula `cell_count()` implements. Parsing
    `grid_side` rather than `cell_count` on purpose: the arms are literals, while
    `cell_count` is arithmetic that a regex would have to re-implement badly.
    The formula is asserted against the crate's own doc-comment values by the
    crate's own unit tests (`WorldScale::Megaplanet.cell_count() == 16384`), so
    this side is pinned twice.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            src = fh.read()
    except OSError:
        return {}
    # `grid_side` is the first fn with WorldScale arms mapping to a bare integer;
    # `tag()` also has such arms, so scope to the grid_side body.
    start = src.find("fn grid_side")
    if start < 0:
        return {}
    end = src.find("\n    }", start)
    if end < 0:
        # Bail rather than widen. Without this the fallback made `body` the REST OF
        # THE FILE, so `tag()`'s `WorldScale::X => 0..5` arms overwrote the real grid
        # sides — yielding nonsense counts and a finding that blames the band instead
        # of the parse. Returning {} makes `check_scale_band` emit its explicit
        # "could not parse the code side" finding, which names the real cause.
        return {}
    body = src[start:end]
    out: dict[str, int] = {}
    for name, g in GRID_ARM.findall(body):
        g = int(g)
        out[name] = (g - 2) * (g - 2) + 4 * (g - 1)
    return out


def parse_scale_decl(text: str):
    """(band, production, non_production) from the machine-read block, or None."""
    m = SCALE_BLOCK.search(text)
    if not m:
        return None
    body = m.group("body")
    bm = BAND_RE.search(body)
    if not bm:
        return None
    band = (int(bm.group(1)), int(bm.group(2)))
    lists: dict[str, list[str]] = {"production": [], "non_production": []}
    current = None
    for raw in body.splitlines():
        line = raw.rstrip()
        key = re.match(r"^\s*(production|non_production):\s*$", line)
        if key:
            current = key.group(1)
            continue
        if current:
            item = re.match(r"^\s*-\s*(\w+)\s*:\s*(\d+)", line)
            if item:
                lists[current].append((item.group(1), int(item.group(2))))
                continue
            bare = re.match(r"^\s*-\s*(\w+)\s*$", line)
            if bare:
                # A name with no count is a HALF-declaration. Accept it so the
                # caller can report it, rather than dropping it silently.
                lists[current].append((bare.group(1), None))
                continue
            if line.strip() and not line.lstrip().startswith("#"):
                current = None
    return band, lists["production"], lists["non_production"]


def check_scale_band(corpus: str, findings: list) -> dict:
    """Join GEO_001's declaration to the generator's real cell counts."""
    stats = {"declared": 0, "verified": 0}
    geo = os.path.join(corpus, GEO_REL)
    if not os.path.isfile(geo):
        return stats
    rel = GEO_REL.replace(os.sep, "/")
    decl = parse_scale_decl(read_text(geo))
    if decl is None:
        findings.append((rel, 0, "scale-band-drift",
                         "no parseable `geo-scale-band` block — the production-scale "
                         "declaration (GEO-D14/D15) is the check's doc-side input; "
                         "without it this guard is silently uncovered"))
        return stats
    band, production, non_production = decl
    counts = world_scale_cell_counts()
    if not counts:
        findings.append((rel, 0, "scale-band-drift",
                         f"could not parse WorldScale::grid_side arms from "
                         f"{os.path.relpath(WORLD_SCALE_RS, REPO_ROOT)} — the code-side "
                         f"input is missing, so the check cannot be satisfied by the doc alone"))
        return stats
    lo, hi = band
    stats["declared"] = len(production) + len(non_production)

    def _declared_count_ok(name, declared, where):
        """The doc's own number vs the generator's. Added after a probe showed an
        in-band grid_side change (Region 45->46, 2025->2116 cells) passed clean
        while GEO_001 still said "2025 cells" — the numbers were unguarded prose."""
        if declared is None:
            findings.append((rel, 0, "scale-band-drift",
                             f"`{name}` is listed under `{where}` with NO cell count. "
                             f"Write `- {name}: {counts.get(name, '<n>')}` — a name-only "
                             f"row leaves the number unchecked, which is how the six "
                             f"counts in this block drifted as prose until 2026-07-30"))
            return
        if declared != counts[name]:
            findings.append((rel, 0, "scale-band-drift",
                             f"`{name}` is declared as {declared} cells but the generator "
                             f"computes {counts[name]} from its own `grid_side` arm "
                             f"((g-2)^2 + 4*(g-1)). One of the two moved without the other"))

    for name, declared in production:
        if name not in counts:
            findings.append((rel, 0, "scale-band-drift",
                             f"declares `{name}` a PRODUCTION scale, but no such "
                             f"`WorldScale` variant exists in the generator "
                             f"(have: {', '.join(sorted(counts))})"))
            continue
        stats["verified"] += 1
        _declared_count_ok(name, declared, "production")
        n = counts[name]
        if not (lo <= n <= hi):
            findings.append((rel, 0, "scale-band-drift",
                             f"`{name}` is declared PRODUCTION but its real cell count "
                             f"{n} is outside the declared band [{lo}, {hi}] — either the "
                             f"band moves (and `cell_count_out_of_bounds` with it) or the "
                             f"scale is not production"))
    for name, declared in non_production:
        if name not in counts:
            findings.append((rel, 0, "scale-band-drift",
                             f"declares `{name}` non-production, but no such `WorldScale` "
                             f"variant exists — a stale exclusion hides a real one"))
            continue
        stats["verified"] += 1
        _declared_count_ok(name, declared, "non_production")
    declared_names = {n for n, _ in production} | {n for n, _ in non_production}
    unlisted = sorted(set(counts) - declared_names)
    if unlisted:
        findings.append((rel, 0, "scale-band-drift",
                         f"generator has scale(s) the declaration does not classify: "
                         f"{', '.join(unlisted)}. A new variant is production-or-not by "
                         f"DECISION, never by default — that default is how `Gigaplanet` "
                         f"came to violate the band unnoticed"))
    return stats


# ── selftest ──────────────────────────────────────────────────────────────
def selftest() -> int:
    """Prove the corpus-enum source reds on its defect AND stays silent on each
    guard. Modelled on `amendment-rot-gate.py --selftest`.

    Every guard here exists because RUNNING the check found the case, not because
    someone imagined it. A guard proven only by the absence of complaints is not
    proven — three of the five cases below must produce NO finding, and those are
    the ones most likely to rot into a permanently-silent check.
    """
    import tempfile
    from collections import Counter

    failures = []

    def run(md: str):
        found: list = []
        counters = {"symbol_prefixes": Counter(), "count_assertions": 0,
                    "count_checked": 0, "count_checked_corpus": 0}
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "x.md")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(md)
            lines = md.splitlines()
            scan_file(path, "x.md", lines, ("count",), set(), {}, "",
                      found, counters, {}, corpus_enum_arities(lines))
        return [f for f in found if f[2] == "count-drift"]

    cases = (
        # (label, markdown, must_red)
        ("the defect (REC-98): a claim disagreeing with the file's own block",
         "`Widget` (3 variants)\n\n```rust\npub enum Widget { A, B, C, D, E }\n```\n", True),
        ("LOOSE form: bold symbol, count a table cell away (the EF_001 shape)",
         "| **Widget** | sum type | 3 variants V1 |\n\n```rust\npub enum Widget { A, B, C, D, E }\n```\n", True),
        ("GUARD elision: `...` marks an illustrative body, not a declaration",
         "`Gadget` (2 variants)\n\n```rust\npub enum Gadget {\n    A,\n    ...\n}\n```\n", False),
        # The stripper's REAL failure mode. A commented-OUT enum is skipped by the
        # parser anyway, so the first version of this case ("// pub enum Doohickey
        # { A, B, C, D, E }") proved NOTHING — found by disarming the stripper and
        # watching this suite still pass, i.e. by bite-testing the bite test. The
        # case that genuinely depends on stripping is a trailing comment that LOOKS
        # like variants: `A,   // B, C, D` parses as THREE without it, one with.
        ("GUARD comments: a trailing comment must not inflate the count (1 vs 3)",
         "`Doohickey` (1 variant)\n\n```rust\npub enum Doohickey {\n    A,   // B, C, D are reserved\n}\n```\n", False),
        ("GUARD version-partition: `// V2+` means there is NO single arity",
         "`Memo` (4 variants)\n\n```rust\npub enum Memo {\n    // V1\n    A, B, C, D,\n    // V2+ additive\n    E, F,\n}\n```\n", False),
        ("GUARD ambiguity: two declared enums on one line -> skip, never guess",
         "| **Widget** | vs `Gizmo` | 3 variants |\n\n```rust\npub enum Widget { A, B, C, D, E }\n```\n"
         "```rust\npub enum Gizmo { A, B, C }\n```\n", False),
        ("a correct claim stays silent",
         "`Sprocket` (4 variants)\n\n```rust\npub enum Sprocket { A, B, C, D }\n```\n", False),
    )

    for label, md, must_red in cases:
        red = bool(run(md))
        if red != must_red:
            failures.append(
                f"count/corpus: {label} -> {'RED' if red else 'silent'}, "
                f"expected {'RED' if must_red else 'silent'}")

    if failures:
        print("SELFTEST FAILED — a check that cannot fail is not a check (NV-1):")
        for f in failures:
            print(f"  x {f}")
        return 1
    print(f"design-lint selftest: OK — {len(cases)} count-source cases behaved as "
          f"specified (2 red on their defect, 5 silent through their guards)")
    return 0


# ── main ──────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        prog="design-lint.py", add_help=True,
        description="Layer-1 mechanical lint for the LLM MMO RPG design corpus.")
    ap.add_argument("--path", default=DEFAULT_CORPUS,
                    help="corpus root (default: docs/03_planning/LLM_MMO_RPG)")
    ap.add_argument("--check", default=",".join(ALL_CHECKS),
                    help=f"comma-separated subset of: {','.join(ALL_CHECKS)}")
    ap.add_argument("--allowlist", default=None,
                    help="prefix allowlist JSON (default: scripts/design-lint.allow.json)")
    ap.add_argument("--max-print", type=int, default=200,
                    help="max findings to print (0 = unlimited; default 200)")
    ap.add_argument("--staged", action="store_true",
                    help="scan only STAGED .md files under the corpus (pre-commit scope)")
    ap.add_argument("--warn-check", default="",
                    help="comma-separated checks whose findings WARN instead of "
                         "failing (still printed; exit stays 0 if only these fire)")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the count corpus-source reds on its defect and "
                         "stays silent through each guard")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    checks = tuple(c.strip() for c in args.check.split(",") if c.strip())
    bad = [c for c in checks if c not in ALL_CHECKS]
    if bad or not checks:
        die(f"unknown --check value(s): {','.join(bad) or '(none)'} "
            f"(valid: {','.join(ALL_CHECKS)})")

    warn_checks = tuple(c.strip() for c in args.warn_check.split(",") if c.strip())
    bad_warn = [c for c in warn_checks if c not in ALL_CHECKS]
    if bad_warn:
        die(f"unknown --warn-check value(s): {','.join(bad_warn)} "
            f"(valid: {','.join(ALL_CHECKS)})")
    warn_kinds = {KIND_OF_CHECK[c] for c in warn_checks if c in KIND_OF_CHECK}

    corpus = os.path.abspath(args.path)
    if not os.path.isdir(corpus):
        die(f"corpus path is not a directory: {corpus}")

    allow = load_allowlist(args.allowlist or DEFAULT_ALLOWLIST,
                           explicit=args.allowlist is not None)

    registered: set[str] = set()
    if "symbol" in checks:
        catalog = os.path.join(corpus, CATALOG_REL)
        if not os.path.isfile(catalog):
            die(f"id catalog not found (needed by symbol check): {catalog}")
        registered = registered_prefixes(catalog)

    matrix_text = ""
    if "registration" in checks:
        matrix = os.path.join(corpus, MATRIX_REL)
        if not os.path.isfile(matrix):
            die(f"ownership matrix not found (needed by registration check): {matrix}")
        matrix_text = read_text(matrix)

    findings: list[tuple[str, int, str, str]] = []
    counters = {"symbol_prefixes": Counter(), "count_assertions": 0,
                "count_checked": 0, "count_checked_corpus": 0}
    enum_arities = rust_enum_arities() if "count" in checks else {}
    n_files = 0
    source = iter_staged_md_files(corpus) if args.staged else iter_md_files(corpus)
    for path in source:
        n_files += 1
        rel = os.path.relpath(path, corpus).replace(os.sep, "/")
        lines = read_text(path).splitlines()
        # Per-file: enums this document declares in its own rust blocks.
        file_enums = corpus_enum_arities(lines) if "count" in checks else {}
        scan_file(path, rel, lines, checks, registered, allow, matrix_text,
                  findings, counters, enum_arities, file_enums)

    scale_stats = check_scale_band(corpus, findings) if "scale-band" in checks else {}

    # ── report ────────────────────────────────────────────────────────────
    scope = "STAGED" if args.staged else "all"
    print(f"design-lint: scanned {n_files} {scope} .md files under {corpus}")
    print(f"  checks: {', '.join(checks)}"
          + (f" (warn-only: {', '.join(warn_checks)})" if warn_checks else ""))
    if "symbol" in checks:
        print(f"  registered prefixes (id catalog): {len(registered)}"
              f" · allowlisted: {len(allow)}")

    shown = findings if args.max_print == 0 else findings[: args.max_print]
    for rel, n, kind, msg in shown:
        print(f"{rel}:{n}: [{kind}] {msg}")
    if len(findings) > len(shown):
        print(f"... and {len(findings) - len(shown)} more "
              f"(rerun with --max-print 0 for all)")

    by_kind = Counter(k for _, _, k, _ in findings)
    print("\n── summary ──")
    if "symbol" in checks:
        print(f"unregistered-prefix: {by_kind.get('unregistered-prefix', 0)} finding(s)"
              f" across {len(counters['symbol_prefixes'])} prefix(es)")
        top = counters["symbol_prefixes"].most_common(15)
        if top:
            print("  top prefixes: " + " · ".join(f"{p}×{c}" for p, c in top))
    if "link" in checks:
        print(f"broken-link: {by_kind.get('broken-link', 0)} finding(s)")
    if "registration" in checks:
        print(f"phantom-registration: {by_kind.get('phantom-registration', 0)} finding(s)")
    if "count" in checks:
        print(f"count-drift: {by_kind.get('count-drift', 0)} finding(s) "
              f"({counters['count_checked']} claim(s) verified against a real Rust enum, "
              f"{counters['count_checked_corpus']} against a spec-only enum declared in the "
              f"same doc; {counters['count_assertions']} count-style phrases seen overall)")

    if "scale-band" in checks:
        print(f"scale-band-drift: {by_kind.get('scale-band-drift', 0)} finding(s) "
              f"({scale_stats.get('verified', 0)} of {scale_stats.get('declared', 0)} "
              f"declared scale(s) joined to a real WorldScale variant)")

    hard = [f for f in findings if f[2] not in warn_kinds]
    soft = [f for f in findings if f[2] in warn_kinds]
    if soft:
        print(f"\ndesign-lint: WARN — {len(soft)} finding(s) in warn-only "
              f"check(s): {', '.join(warn_checks)}")
    if hard:
        print(f"design-lint: FAIL — {len(hard)} finding(s)")
        return 1
    print("design-lint: OK — no blocking findings" if soft
          else "\ndesign-lint: OK — no findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
