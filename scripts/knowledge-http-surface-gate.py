#!/usr/bin/env python3
"""knowledge-http-surface-gate.py — enforce INV-KAL's HTTP-surface half (D6 mechanism ii).

Part of the Incremental Temporal Knowledge Architecture (spec
docs/specs/2026-06-29-incremental-temporal-knowledge-architecture.md §6D, §12.5.5).
Companion to scripts/knowledge-access-gate.py (the TABLE-READ half).

INV-KAL: entity/lore KNOWLEDGE is read through the Knowledge Access Layer (the
knowledge-gateway, KAL), never by a consumer reaching the owning services' bespoke
`/internal/*` KNOWLEDGE routes over HTTP. This gate is the HTTP-SURFACE half: it
FAILS when a CONSUMER service references one of the owning services' bi-temporal
knowledge-read `/internal/*` endpoints that the KAL federates — read those through
`KNOWLEDGE_GATEWAY_URL` (`/v1/kal/...`) instead.

🔴 **The guarded set is DERIVED from the KAL's own read controller, not written here.**
It used to be a list in this file, and the list went stale: measured 2026-08-22 (T55) the
KAL federated 11 upstream reads and this gate guarded 7. `canonical-translation`,
`entities/by-ids` and `state` were federated and UNGUARDED, so a consumer bypassing the
KAL on any of them was invisible while this gate printed PASS. Every path
`kal-read.controller.ts` calls is by definition a federated read, so a read is guarded the
day it is federated rather than the day someone remembers this file. Run `--selftest`.

⚠️ **What deriving cannot do**: it cannot guard a knowledge read the KAL does not federate.
composition-service reads `/internal/context/build`, `/internal/context/glossary-semantic`
and `/internal/projects/{id}/fact-for-check` directly, and the KAL offers none of the three
— so no rule in this file can cover them. Closing that needs the KAL to federate them,
which is a design decision and not a gate change. Recorded rather than hand-listed here,
because adding them to a list in this file would make the gate look complete while the
reads stayed exactly as direct as they are.

SCOPE (deliberately matched to the table-read gate): INV-KAL governs the DERIVED
bi-temporal knowledge substrate — the EAV-projected facts + the KG. The AUTHORED
entity CATALOG (`glossary_entities`: name / kind / short_description, served by the
`/internal/books/{book}/entities` LIST endpoint that KAL `roster` thins to id+name)
is NOT part of that substrate — it is the authored source consumers may read
directly, exactly as the table-read gate exempts `glossary_entities`. So the LIST
endpoint is NOT flagged here; only the bi-temporal reads above are.

The owning services (glossary, knowledge) themselves and the KAL (knowledge-gateway)
are exempt — they ARE the endpoints / the federator.

Mirrors scripts/knowledge-access-gate.py (cross-platform; allowlist + --staged).

Usage:
  python scripts/knowledge-http-surface-gate.py            # full scan (CI / manual)
  python scripts/knowledge-http-surface-gate.py --staged   # only git-staged files (pre-commit)
  python scripts/knowledge-http-surface-gate.py --selftest # prove the derivation can go red

Exit 0 = clean (or allowlisted-only). Exit 1 = violation.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SEARCH_DIRS = ("services",)
SCAN_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".mjs")
EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv",
    "dist", "build", ".next", ".git", "vendor", "coverage",
}

# Owners + the KAL itself are exempt: they ARE the endpoints / the federator.
EXEMPT_SERVICE_PREFIXES = (
    "services/glossary-service/",     # owns the glossary /internal routes
    "services/knowledge-service/",    # owns the knowledge /internal routes
    "services/knowledge-gateway/",    # the KAL — the SANCTIONED federator of these routes
)

# Allowlisted KNOWN outliers (tracked, not enforced) — keep tight + comment each.
ALLOWLIST_PREFIXES: tuple[str, ...] = (
    # (none — the bi-temporal knowledge reads are fully migrated to the KAL.)
)

# ── prose is not a call site ─────────────────────────────────────────
#
# ⚠️ The scan used to match RAW LINES, and the derived set walked straight into it: two
# services carry a docstring naming `/internal/books/{book_id}/entities/by-ids` while both
# actually call the KAL's `/v1/kal/books/{id}/cast/by-ids`. Reporting those is worse than a
# false positive — the cheapest way to make the gate green is to edit the sentence, which
# deletes the explanation and changes nothing about the code.
_LINE_COMMENT = re.compile(r"(?://|#).*$")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_PY_DOCSTRING = re.compile(r'"""(?:.|\n)*?"""' + "|" + r"'''(?:.|\n)*?'''")


def strip_prose(src: str) -> str:
    """`src` with comments and Python docstrings blanked, LINE COUNT preserved.

    Line numbers have to survive so a violation still points at the right line — replacing a
    multi-line docstring with nothing would shift every number after it.
    """
    def _blank(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    src = _PY_DOCSTRING.sub(_blank, src)
    src = _BLOCK_COMMENT.sub(_blank, src)
    return "\n".join(_LINE_COMMENT.sub("", line) for line in src.split("\n"))


# ── the guarded set, DERIVED from the KAL's own read controller ───────
#
# 🔴 **This list used to be hand-written, and it was short.** Measured 2026-08-22 (T55): the
# KAL federates **11** distinct upstream read paths and the hand-list guarded **7**. Three real
# federated reads — `canonical-translation`, `entities/by-ids` and `state` — were unguarded, so
# a consumer calling one of them past the KAL was invisible to this gate while the gate printed
# PASS. That is the failure mode a hand-list always has: it is correct on the day it is written.
#
# The KAL's read controller IS the manifest. Every upstream path it calls is, by definition, a
# federated read; deriving from it means a read added to the KAL is guarded the day it is
# federated rather than the day someone remembers this file.
#: The KAL's read manifest. A GLOB, not a filename — T55/h added
#: `kal-project-read.controller.ts` for the project-scoped axis, and a gate pinned to the one
#: original file would have kept reporting 11 federated reads while 13 existed, so the two new
#: ones would NOT have been guarded and consumers could keep calling them direct. The manifest
#: growing is exactly the event this gate is derived to survive; hard-coding one path made the
#: derivation only as good as a hand-list one level up.
KAL_READ_CONTROLLER_DIR = os.path.join("services", "knowledge-gateway", "src", "kal")
KAL_READ_CONTROLLER_GLOB = "*read*.controller.ts"


def _kal_read_controllers() -> list[str]:
    """Every KAL read controller, sorted. Empty is an ERROR the caller refuses to run on."""
    import fnmatch
    root = os.path.join(REPO_ROOT, KAL_READ_CONTROLLER_DIR)
    if not os.path.isdir(root):
        return []
    return sorted(
        os.path.join(KAL_READ_CONTROLLER_DIR, f)
        for f in os.listdir(root)
        if fnmatch.fnmatch(f, KAL_READ_CONTROLLER_GLOB)
    )


#: Kept for the error text and for tests that name the original.
KAL_READ_CONTROLLER = os.path.join(
    "services", "knowledge-gateway", "src", "kal", "kal-read.controller.ts",
)

#: The ONE deliberate exclusion, named rather than silently absent. The authored entity CATALOG
#: is not part of the bi-temporal substrate INV-KAL governs (see the module header), so the
#: `/internal/books/{book}/entities` LIST endpoint is not flagged — exactly as the table-read
#: gate exempts `glossary_entities`. It is written as a rule the derivation applies, so the
#: exclusion survives the list changing underneath it.
_AUTHORED_CATALOG_TAIL = "/entities"


def _derive_federated_reads(controller_src: str) -> list[str]:
    """The upstream `/internal/...` paths the KAL read controller calls, normalised.

    Template holes (`${bookId}`) become a wildcard; query strings are dropped. Returns the
    paths in first-seen order so the gate's own output is stable.
    """
    out: list[str] = []
    for raw in re.findall(r"`(/internal/[^`]*)`", controller_src):
        path = raw.split("?")[0]
        path = re.sub(r"\$\{[^}]*\}", "{}", path).rstrip("{}").rstrip("/")
        if not path or path in out:
            continue
        if path.endswith(_AUTHORED_CATALOG_TAIL):
            continue          # the authored catalog — see the header, and the note above
        out.append(path)
    return out


def _to_pattern(paths: list[str]) -> re.Pattern[str]:
    """One alternation matching any of `paths`, with `{}` standing for a path segment."""
    if not paths:
        # ⚠️ `re.compile("(?:)")` matches EVERY line, so an empty guarded set would flag the
        # whole repo rather than guarding nothing. `_load_covered` checks emptiness too, but
        # its check does not protect a second caller — the selftest found this one.
        raise ValueError(
            "refusing to build a guarded-set pattern from zero paths: `(?:)` matches every "
            "line, so the gate would flag the whole repo instead of guarding nothing"
        )
    parts = []
    for path in paths:
        # `[^\s"'`/]+` for a hole: an id, an f-string interpolation, a `${...}` — but never a
        # slash, so `/entities/{}/facts` cannot match `/entities/search/x/facts`.
        frag = re.escape(path).replace(r"\{\}", "[^\\s\"'`/]+")
        parts.append(frag + r"\b")
    return re.compile("(?:" + "|".join(parts) + ")")


def _load_covered() -> tuple[re.Pattern[str], list[str]]:
    controllers = _kal_read_controllers()
    try:
        if not controllers:
            raise OSError(f"no {KAL_READ_CONTROLLER_GLOB} under {KAL_READ_CONTROLLER_DIR}")
        src = chr(10).join(
            open(os.path.join(REPO_ROOT, c), encoding="utf-8", errors="replace").read()
            for c in controllers
        )
    except OSError as exc:
        raise SystemExit(
            f"[knowledge-http-surface-gate] cannot read the KAL read controller at "
            f"{KAL_READ_CONTROLLER}: {exc}. The guarded set is DERIVED from it — refusing to "
            f"run against an empty manifest, which would pass everything."
        ) from exc
    # The manifest is read as CODE, not prose. The first derivation picked up
    # `/internal/.../entities/by-ids` from a comment in the controller — an ellipsis where a
    # book id belongs — and turned it into a guarded pattern. A gate whose guarded set can be
    # extended by writing a sentence is the same defect as one that fires on a sentence.
    paths = _derive_federated_reads(strip_prose(src))
    if not paths:
        raise SystemExit(
            f"[knowledge-http-surface-gate] derived ZERO federated reads from "
            f"{KAL_READ_CONTROLLER}. A gate with an empty pattern passes every consumer — "
            f"refusing rather than reporting a clean scan."
        )
    return _to_pattern(paths), paths



KAL_COVERED, KAL_COVERED_PATHS = _load_covered()




def is_test_file(rel: str) -> bool:
    base = os.path.basename(rel)
    return (
        "/tests/" in rel or "/test/" in rel or "/fixtures/" in rel
        or "/__fixtures__/" in rel or "/__mocks__/" in rel
        or rel.endswith("_test.go")
        or base.startswith("test_")
        or base.endswith((".spec.ts", ".spec.tsx", ".test.ts", ".test.tsx"))
        or base == "conftest.py"
    )


def scan_file(path: str, rel: str) -> list[tuple[int, str, str]]:
    if is_test_file(rel) or rel.startswith(ALLOWLIST_PREFIXES) or rel.startswith(EXEMPT_SERVICE_PREFIXES):
        return []
    out: list[tuple[int, str, str]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            src = fh.read()
        for n, line in enumerate(strip_prose(src).split("\n"), 1):
            if KAL_COVERED.search(line):
                out.append((n, rel, line.strip()[:160]))
    except OSError:
        pass
    return out


def iter_full_scan():
    for d in SEARCH_DIRS:
        root = os.path.join(REPO_ROOT, d)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [x for x in dirnames if x not in EXCLUDE_DIRS]
            for fn in filenames:
                if fn.endswith(SCAN_EXTS):
                    full = os.path.join(dirpath, fn)
                    yield full, os.path.relpath(full, REPO_ROOT).replace("\\", "/")


def iter_staged():
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return
    for rel in out.splitlines():
        rel = rel.strip().replace("\\", "/")
        if rel.endswith(SCAN_EXTS) and rel.startswith(SEARCH_DIRS):
            full = os.path.join(REPO_ROOT, rel)
            if os.path.isfile(full):
                yield full, rel


# ── T55: the SECOND half of INV-KAL — every DIRECT knowledge read is declared ────────────
#
# The check above catches a consumer reaching one of the reads the KAL federates. It is
# silent about a knowledge read the KAL does NOT federate, and that silence is where the
# invariant actually leaks: `/internal/projects/{}/fact-for-check` was watched firing in
# live logs while this gate reported PASS, because it is not in the controller and so not in
# the derived set.
#
# 📐 **The row estimated 13 paths, in one service. Measured 2026-08-22 it is 42, across 12.**
# The 13 was composition-service's own client; every other consumer went uncounted. Migrating
# 42 routes is not a gate's job, and §8.3's instruction is "migrate or explicitly EXEMPT" —
# so this is the exemption half, built so the exemption cannot rot:
#
#   the OWNER's routes   derived from knowledge-service's own APIRouter prefixes + decorators
#   the CONSUMERS        derived by scanning every non-test, non-owner file for those paths
#   the LEDGER           hand-written REASONS, but never a hand-written scope
#
# Both directions fail. A new consumer path that is not in the ledger fails CLOSED (the
# gate cannot know whether it is a read). A ledger entry nothing reaches any more also
# fails, because a stale exemption is how a list stops describing the code — the same
# defect this gate's own hand-list had before it was derived.
#
# ⚠️ The reasons are NOT decisions about architecture. `read-not-yet-federated` records a
# debt in the place a reader will look, instead of leaving it invisible; it does not license
# the call.

_OWNER_ROUTERS = os.path.join("services", "knowledge-service", "app", "routers")

_APIROUTER = re.compile(r"APIRouter\((.*?)\)", re.S)
_PREFIX = re.compile(r"""prefix\s*=\s*["']([^"']*)["']""")
_ROUTE_DEC = re.compile(r"""@router\.(?:get|post|put|patch|delete)\(\s*["']([^"']*)["']""")


def _normalise(path: str) -> str:
    """`/internal/books/{book_id}/x` and `/internal/books/${bookId}/x` → one shape."""
    path = re.sub(r"\$\{[^}]*\}", "{}", path)
    path = re.sub(r"\{[^}]*\}", "{}", path)
    return path.rstrip("/")


def derive_owner_routes(router_dir: str | None = None) -> set[str]:
    """Every `/internal/*` route knowledge-service actually serves, from its own source.

    Derived rather than listed because the question "is this path knowledge-service's?" is
    the one a hand-list gets wrong first — a route renamed in the service leaves the list
    naming an endpoint that no longer exists, and the gate then guards nothing while
    reporting a number.
    """
    root = router_dir or os.path.join(REPO_ROOT, _OWNER_ROUTERS)
    out: set[str] = set()
    if not os.path.isdir(root):
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            try:
                src = open(os.path.join(dirpath, fn), encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            m = _APIROUTER.search(src)
            prefix = ""
            if m:
                pm = _PREFIX.search(m.group(1))
                if pm:
                    prefix = pm.group(1)
            for suffix in _ROUTE_DEC.findall(src):
                full = prefix + suffix
                if full.startswith("/internal"):
                    out.add(_normalise(full))
    return out


#: Every direct knowledge `/internal/*` call a consumer makes, with WHY it is not a KAL read.
#: Measured 2026-08-22. Keys are normalised paths; values are (class, reason).
#:
#: classes:
#:   write        a mutation or a job dispatch — INV-KAL governs READS
#:   compute      the consumer sends its own payload and gets a derived answer back; no
#:                bi-temporal entity state is returned
#:   admin        an operator/erasure path, deliberately not user-facing
#:   federate     DECIDED (§8.6) to belong behind the KAL: its RESPONSE carries a projection
#:                of knowledge state — the class the 10 already-federated reads all share.
#:                OWED WORK, named on every run.
#:   ops / meta   operational status, a listing, a run artefact, or project metadata.
#:   read-pg      reads knowledge-service but is served from Postgres, not the graph.
#:
#: ⚠️ `read-owed` deliberately claims less than it first did. The first cut called these
#: "a genuine bi-temporal read", and that is not mechanically derivable at this granularity —
#: two probes over the same ten paths disagree, and BOTH are wrong in a known way:
#:
#:     3 of 10   scanning the route handler's own body. MISSES delegation: `/internal/
#:               context/build` shows only `ProjectsRepo` for 60 lines and reaches the graph
#:               two hops down, through `app.context.modes.full`.
#:     9 of 10   following the module's import closure. Attributes any graph use ANYWHERE in
#:               the closure to EVERY route in the module, and resolved `/internal/knowledge/
#:               jobs` "via app.routers.internal_wiki", which is nonsense.
#:
#: So the ledger records what is established — the call is direct, and the graph is reachable
#: from it — and leaves "is this a bi-temporal read that belongs behind the KAL" to the
#: per-route judgement §8.3 actually asks for. A count that reads as settled when it is not is
#: the defect this plan keeps finding in other people's numbers; it applies to mine.
#: How many routes §8.6 DECIDED belong behind the KAL and are not yet federated.
#:
#: A ratchet, because without one the decision is editable in silence: re-labelling
#: `fact-for-check` from `federate` to `ops` would drop the owed count with nothing going red,
#: and §8.6 would still read as enforced while enforcing less. Rule 5 — this number moves in
#: the SAME COMMIT as the federation that moves it, and only DOWN.
#: 4 -> 3 at T55/e (`timeline`), 3 -> 1 at T55/h (`fact-for-check` +
#: `glossary-semantic`, on the new project-scoped controller). Each drop lands in the
#: same commit as the federation that caused it (rule 5).
#:
#: 1 -> 0 at T55/i. `wiki-neighborhood` was recorded as fitting NEITHER axis because its
#: caller takes only a `glossary_entity_id` — measured at the wrong boundary, since
#: `build_context_brief(book_id, ...)` two frames up has the book and merely dropped it.
#:
#: ZERO is the resting state, and the ratchet still has teeth: a NEW direct read that §8.6
#: would class `federate` raises this above 0 and reds.
MAX_FEDERATE_OWED = 0

DIRECT_INTERNAL_LEDGER: dict[str, tuple[str, str]] = {
    # ── federate: DECIDED (§8.6) to belong behind the KAL ────────────────────────────────
    # ── compute: reads knowledge, returns a rendered artefact ────────────────────────────
    "/internal/context/build": (
        "compute", "§8.6: ContextBuildResponse{mode, context, token_count, stable_context, "
        "volatile_context} — a RENDERED prompt with token accounting, not a projection of "
        "state. It reads knowledge heavily, which is why an import probe flags it; a consumer "
        "cannot re-window a string, so the spoiler window belongs inside the owner. Revisit "
        "if `sections` ever carries structured entity data."),
    "/internal/extraction/extract-item": ("compute", "LLM extraction over supplied text"),
    "/internal/extraction/tag-beats": ("compute", "tags supplied beats"),
    "/internal/extraction/tag-motifs": ("compute", "tags supplied motifs"),
    "/internal/extraction/tag-threads": ("compute", "tags supplied threads"),
    "/internal/extraction/motif-beats": ("compute", "derives motif/beat pairs"),
    "/internal/extraction/causal-edges": ("compute", "derives causal edges"),
    "/internal/extraction/causal-motif-pairs": ("compute", "derives causal motif pairs"),
    "/internal/extraction/summarize-message": ("compute", "summarises supplied text"),
    "/internal/extraction/resolve-schema": ("compute", "resolves a schema for a run"),
    "/internal/parse": ("compute", "document parsing; no knowledge state"),
    "/internal/parse/chapter": ("compute", "chapter parsing"),
    "/internal/parse/pdf-chunk": ("compute", "PDF chunking"),
    "/internal/parse/pdf-peek": ("compute", "PDF header peek"),
    # ── ops: operational status, listings and run artefacts ──────────────────────────────
    "/internal/knowledge/projects/{}/extraction-status": (
        "ops", "§8.6: {active, last_outcome} — operational status of a run."),
    "/internal/knowledge/jobs": ("ops", "§8.6: an untyped job listing. Operational."),
    "/internal/extraction/runs/{}/sample": (
        "ops", "§8.6: RunSampleResponse keyed by `config_hash` — what a RUN produced, not "
        "what the graph holds."),
    # ── meta / read-pg: not the bi-temporal substrate ────────────────────────────────────
    "/internal/context/project-book/{}": (
        "meta", "§8.6: ProjectBookResponse{book_id} — one id, project metadata."),
    # The ONE case both T55/c probes agree on: the handler reads `get_knowledge_pool` and the
    # import closure reaches no graph symbol at all. Postgres-backed despite the name.
    "/internal/books/{}/kg-state": ("read-pg", "per-book KG state, served from Postgres"),
    # ── write ────────────────────────────────────────────────────────────────────────────
    "/internal/extraction/persist-pass2": ("write", "persists extracted pass-2 output"),
    "/internal/extraction/glossary-sync-entity": ("write", "syncs a glossary anchor"),
    "/internal/knowledge/enriched-writeback": ("write", "admits enrichment, quarantined"),
    "/internal/knowledge/enriched-promote": ("write", "canonises enrichment"),
    "/internal/knowledge/enriched-retract": ("write", "retracts enrichment"),
    "/internal/knowledge/projects/{}/dispatch-extraction": ("write", "dispatches a run"),
    "/internal/knowledge/projects/{}/extraction/cancel": ("write", "cancels a run"),
    "/internal/knowledge/projects/{}/set-campaign-models": ("write", "sets run models"),
    "/internal/projects/{}/backfill-glossary-passages": ("write", "a backfill"),
    "/internal/working-memory/init": ("write", "opens a working-memory session"),
    "/internal/working-memory/tick": ("write", "advances a working-memory session"),
    # ── admin ────────────────────────────────────────────────────────────────────────────
    "/internal/admin/assistant/close-epoch": ("admin", "operator epoch close"),
    "/internal/admin/assistant/erase": ("admin", "erasure — GDPR path"),
    "/internal/admin/assistant/forget-entity": ("admin", "operator forget"),
    "/internal/admin/assistant/invalidate-day": ("admin", "operator invalidation"),
    "/internal/admin/assistant/queue-facts": ("admin", "operator fact queue"),
    "/internal/admin/assistant/recall-facts": ("admin", "operator recall"),
    "/internal/admin/model-deletion/impact": ("admin", "model-deletion impact report"),
    "/internal/admin/model-deletion/cleanup": ("admin", "model-deletion cleanup"),
}


def ledger_duplicate_keys() -> list[str]:
    """Paths written TWICE in `DIRECT_INTERNAL_LEDGER`'s source.

    ⚠️ Found by a bite that failed to bite. Adding a second row for
    `/internal/knowledge/enriched-promote` with a different class changed NOTHING: a Python
    dict literal keeps the last value silently, so the new row was swallowed and the count
    did not move. A ledger where a row can be overwritten without a sound is a ledger whose
    classes describe whatever happened to come last in the file.

    Read from the AST rather than the imported dict, because by the time it is a dict the
    duplicate is already gone — which is exactly why nothing noticed.
    """
    import ast as _ast
    tree = _ast.parse(open(__file__, encoding="utf-8", errors="replace").read())
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.AnnAssign):
            continue
        if not (isinstance(node.target, _ast.Name)
                and node.target.id == "DIRECT_INTERNAL_LEDGER"):
            continue
        if not isinstance(node.value, _ast.Dict):
            continue
        seen, dupes = set(), []
        for k in node.value.keys:
            if isinstance(k, _ast.Constant) and isinstance(k.value, str):
                if k.value in seen:
                    dupes.append(k.value)
                seen.add(k.value)
        return sorted(set(dupes))
    return []


def scan_direct_consumers(files=None, owner_routes=None) -> dict[str, set[str]]:
    """`{normalised path: {consumer service}}` for direct knowledge `/internal` calls.

    `files`/`owner_routes` are injectable so the selftest drives this on fixtures rather
    than on the repo, which passes for its own reasons.
    """
    owned = derive_owner_routes() if owner_routes is None else owner_routes
    if not owned:
        return {}
    hits: dict[str, set[str]] = {}
    source = files if files is not None else iter_full_scan()
    for full, rel in source:
        if (is_test_file(rel) or rel.startswith(ALLOWLIST_PREFIXES)
                or rel.startswith(EXEMPT_SERVICE_PREFIXES)):
            continue
        try:
            raw = open(full, encoding="utf-8", errors="ignore").read() \
                if os.path.isfile(full) else full
        except OSError:
            continue
        # WARNING: `strip_prose` sits OUTSIDE the branch above. The first cut applied it
        # only when reading a real FILE, so a selftest fixture (a plain string) was scanned
        # RAW — the selftest exercised a code path production never takes, and its "a
        # comment is not a call" case passed the wrong function. Found by that case FAILING.
        src = strip_prose(raw)
        for literal in re.findall(r"/internal/[A-Za-z0-9_{}$/.-]+", src):
            norm = _normalise(literal)
            if norm in owned:
                parts = rel.split("/")
                hits.setdefault(norm, set()).add(parts[1] if len(parts) > 1 else rel)
    return hits


def check_ledger(reached: dict[str, set[str]], federated: list[str]) -> list[str]:
    """Problems with the ledger, as printable lines. Empty means it describes the code.

    A path the KAL federates is NOT expected here — the first check already forbids reaching
    it directly, and listing it would read as permission.
    """
    problems: list[str] = []
    fed = set(federated)
    for path in sorted(reached):
        if path in fed:
            continue
        if path not in DIRECT_INTERNAL_LEDGER:
            problems.append(
                f"  UNDECLARED  {path}\n"
                f"      reached by: {', '.join(sorted(reached[path]))}\n"
                f"      A consumer calls knowledge-service directly on a path no one has "
                f"classified. Add it to DIRECT_INTERNAL_LEDGER with a class and a reason, "
                f"or route it through the KAL. Fails CLOSED because the gate cannot tell "
                f"whether it is a bi-temporal read.")
    for path in sorted(DIRECT_INTERNAL_LEDGER):
        if path not in reached:
            problems.append(
                f"  STALE       {path}\n"
                f"      No consumer reaches this any more. Remove the entry — a ledger that "
                f"keeps dead rows stops describing the code, which is the hand-list defect "
                f"this gate was derived to escape.")
    return problems


def selftest() -> int:
    """Offline proof that the derivation is real, bounded, and can go red.

    A hand-bite is invisible to CI, and this gate's whole change is that its guarded set is no
    longer something a human wrote down. So the properties that matter are: it DERIVES, it
    derives from CODE, it refuses an empty manifest instead of passing everything, and it does
    not fire on prose.
    """
    ok = True
    print("knowledge-http-surface-gate - selftest (offline)")

    def check(label: str, got, want) -> None:
        nonlocal ok
        good = got == want
        ok = ok and good
        print(f"  {'PASS' if good else 'FAIL'}  {label}: expected {want!r}, got {got!r}")

    controller = (
        "class KalReadController {\n"
        "  a() { return g.get(`/internal/books/${bookId}/entities/${id}/facts?x=1`); }\n"
        "  b() { return g.get(`/internal/books/${bookId}/kg/neighborhood`); }\n"
        "  c() { return g.get(`/internal/books/${bookId}/entities?limit=1`); }\n"
        "  // see also `/internal/books/.../made-up-in-a-comment`\n"
        "}\n"
    )
    derived = _derive_federated_reads(strip_prose(controller))
    check("the manifest yields its federated reads", len(derived), 2)
    check("the authored-catalog LIST is excluded by rule",
          any(p.endswith("/entities") for p in derived), False)
    check("a path named only in a COMMENT is not a federated read",
          any("made-up" in p for p in derived), False)

    pat = _to_pattern(derived)
    check("a consumer calling a federated read is caught",
          bool(pat.search("r = get(f'/internal/books/{b}/entities/{e}/facts')")), True)
    check("the KAL's own /v1/kal path is not caught",
          bool(pat.search("r = get('/v1/kal/books/x/facts')")), False)
    check("the authored LIST is not caught",
          bool(pat.search("r = get(f'/internal/books/{b}/entities')")), False)
    # The hole is one SEGMENT, not "anything": a deeper path must not be swallowed.
    check("a hole does not span a slash",
          bool(pat.search("get('/internal/books/b/entities/search/deep/facts')")), False)

    # ── the property this whole change exists for ────────────────────────────────────────
    grown = controller.replace(
        "}\n", "  d() { return g.get(`/internal/books/${bookId}/lore-digest`); }\n}\n", 1)
    grown_pat = _to_pattern(_derive_federated_reads(strip_prose(grown)))
    check("a read the KAL STARTS federating is guarded with NO gate edit",
          bool(grown_pat.search("get(f'/internal/books/{b}/lore-digest')")), True)

    # ── prose is not a call site ─────────────────────────────────────────────────────────
    doc = '"""Calls: POST /internal/books/{book_id}/entities/{e}/facts\n\nprose.\n"""\nx = 1\n'
    stripped = strip_prose(doc)
    check("a docstring naming a guarded read is not scanned",
          bool(pat.search(stripped)), False)
    check("stripping preserves the LINE COUNT so violations still point at the right line",
          len(stripped.split("\n")), len(doc.split("\n")))
    check("a trailing `# comment` naming a guarded read is not scanned",
          bool(pat.search(strip_prose("x = 1  # /internal/books/b/entities/e/facts"))), False)
    check("...but the CODE on that same line still is",
          bool(pat.search(strip_prose(
              "get('/internal/books/b/entities/e/facts')  # a comment"))), True)

    # ── an empty manifest must REFUSE, not pass everything ───────────────────────────────
    try:
        _to_pattern([])
        empty_pattern_built = True
    except ValueError:
        empty_pattern_built = False
    check("an empty derived set REFUSES rather than matching everything",
          empty_pattern_built, False)

    # ── T55: the ledger half, on FIXTURES ───────────────────────────────────────────────
    # Driven on synthetic sources rather than the repo, because a check run only against a
    # tree that currently passes reports PASS for the tree's reason and not its own.
    router_src = (
        'router = APIRouter(prefix="/internal/knowledge", tags=["k"])' + chr(10)
        + '@router.post("/enriched-writeback")' + chr(10)
        + 'async def wb(): ...' + chr(10)
        + '@router.get("/projects/{project_id}/status")' + chr(10)
        + 'async def st(): ...' + chr(10)
        # A SECOND router with no prefix: proves the /internal filter is applied to the
        # FULL path and not to the decorator's suffix.
        + 'other = APIRouter()' + chr(10)
        + '@other.get("/v1/public")' + chr(10)
        + 'async def nope(): ...' + chr(10)
    )
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, "r.py"), "w", encoding="utf-8") as fh:
            fh.write(router_src)
        owned = derive_owner_routes(td)
    check("the owner's routes are derived from prefix + decorator",
          owned, {"/internal/knowledge/enriched-writeback",
                  "/internal/knowledge/projects/{}/status"})   # /v1/public is not /internal

    # A consumer literal is matched against that derived set, and normalised both ways.
    consumer = ('x = "/internal/knowledge/enriched-writeback"' + chr(10)
                + 'y = f"/internal/knowledge/projects/{pid}/status"' + chr(10))
    reached = scan_direct_consumers(
        files=[(consumer, "services/some-consumer/app/c.py")], owner_routes=owned)
    check("both a literal and an f-string hole reach the owner's routes",
          sorted(reached), ["/internal/knowledge/enriched-writeback",
                            "/internal/knowledge/projects/{}/status"])

    # ⚠️ FAIL CLOSED. An undeclared path is the whole point: the gate cannot tell whether a
    # new direct call is a bi-temporal read, so silence must not be the default.
    # `all_reached` isolates the case under test: without it every ledger row also reports
    # STALE and the one finding being asserted is lost in 42 others.
    all_reached = {p: {"svc"} for p in DIRECT_INTERNAL_LEDGER}
    problems = check_ledger({**all_reached, "/internal/brand/new": {"svc"}}, [])
    check("an UNDECLARED direct call fails closed", len(problems), 1)
    check("...and the message says so", "UNDECLARED" in (problems[0] if problems else ""), True)

    # A stale entry is the hand-list defect this gate was derived to escape, so it fails too.
    stale = check_ledger({p: {"svc"} for p in DIRECT_INTERNAL_LEDGER}, [])
    check("a ledger matching the code exactly has no problems", stale, [])
    problems = check_ledger(
        {p: {"svc"} for p in list(DIRECT_INTERNAL_LEDGER)[1:]}, [])
    check("a ledger entry nothing reaches any more is STALE", len(problems), 1)
    check("...and it says STALE", "STALE" in (problems[0] if problems else ""), True)

    # A path the KAL federates must NOT be demanded in the ledger — the first check already
    # forbids reaching it, and an entry for it would read as permission.
    problems = check_ledger({**all_reached, "/internal/books/{}/entities/{}/facts": {"svc"}},
                            ["/internal/books/{}/entities/{}/facts"])
    check("a KAL-federated path is not demanded in the ledger", problems, [])

    # The §8.6 ratchet, statically. The runtime check needs a scan; this one catches a
    # `federate` row added or re-labelled without `MAX_FEDERATE_OWED` moving with it, which
    # is rule 5 applied to a decision rather than to a count.
    # A row written twice is a row silently discarded — see `ledger_duplicate_keys`.
    check("no ledger path is declared twice", ledger_duplicate_keys(), [])
    declared = [p for p, (cls, _) in DIRECT_INTERNAL_LEDGER.items() if cls == "federate"]
    check("the federate ratchet matches the ledger", len(declared), MAX_FEDERATE_OWED)
    check("every federate row cites the section that decided it",
          all("8.6" in DIRECT_INTERNAL_LEDGER[p][1] for p in declared), True)
    # Every class a row USES must be a known one — a typo'd class would sort into no bucket
    # and quietly stop being counted by the `federate` ratchet.
    #
    # ⚠️ NOT the converse. The first cut asserted the used set EQUALS the known set, and it
    # went red the moment `federate` emptied out at T55/i — which is the migration SUCCEEDING.
    # A class with no members is the resting state for `federate`, so demanding every class
    # stay populated would have made finishing the work look like a regression.
    KNOWN = {"admin", "compute", "federate", "meta", "ops", "read-pg", "write"}
    used = {cls for cls, _ in DIRECT_INTERNAL_LEDGER.values()}
    check("every ledger class is a known one", sorted(used - KNOWN), [])

    # Validated on a case the scanner was NOT derived from: prose.
    commented = ('# calls "/internal/knowledge/enriched-writeback" one day' + chr(10)
                 + 'z = 1' + chr(10))
    check("a path named only in a COMMENT is not a direct call",
          scan_direct_consumers(files=[(commented, "services/c/app/x.py")],
                                owner_routes=owned), {})

    print(f"{chr(10)}  {'all checks passed' if ok else 'SELFTEST FAILED'}")
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    staged = "--staged" in sys.argv
    it = iter_staged() if staged else iter_full_scan()
    violations: list[tuple[int, str, str]] = []
    for full, rel in it:
        violations.extend(scan_file(full, rel))

    if not violations:
        # ── T55: the ledger half. Only meaningful on a FULL scan — a staged run sees the
        # changed files alone, so "no consumer reaches this any more" would fire on every
        # path outside the diff and report the whole ledger stale.
        if not staged:
            reached = scan_direct_consumers()
            problems = check_ledger(reached, KAL_COVERED_PATHS)
            if problems:
                print("[knowledge-http-surface-gate] FAIL — the direct-call ledger "
                      "no longer describes the code:" + chr(10))
                for line in problems:
                    print(line)
                return 1
            owed = sorted(p for p, (cls, _) in DIRECT_INTERNAL_LEDGER.items()
                          if cls == "federate" and p in reached)
            if len(owed) != MAX_FEDERATE_OWED:
                verb = "ROSE to" if len(owed) > MAX_FEDERATE_OWED else "fell to"
                print(f"[knowledge-http-surface-gate] FAIL — §8.6's federate-owed count "
                      f"{verb} {len(owed)} (ratchet {MAX_FEDERATE_OWED}).")
                print("  DOWN means a route was federated: lower the ratchet in this commit "
                      "(rule 5).")
                print("  UP, or a silent re-label, means the decision changed without §8.6 "
                      "changing. Move both.")
                for path in owed:
                    print(f"    federate-owed  {path}")
                return 1
            print(f"[knowledge-http-surface-gate] direct-call ledger {len(reached)} path(s) "
                  f"across {len({s for v in reached.values() for s in v})} consumer service(s), "
                  f"all declared; {len(owed)} DECIDED to belong behind the KAL "
                  f"(§8.6) and not yet federated:")
            for path in owed:
                print(f"    federate-owed  {path}")
        print(f"[knowledge-http-surface-gate] PASS — no consumer hits the "
              f"{len(KAL_COVERED_PATHS)} bi-temporal knowledge /internal reads the KAL "
              f"federates (DERIVED from its read controller, not hand-listed)")
        return 0

    print("[knowledge-http-surface-gate] FAIL — INV-KAL HTTP-surface violations "
          "(read bi-temporal knowledge through the KAL, not the owning service's /internal route):\n")
    for n, rel, line in violations:
        print(f"  [kal-covered-internal-read] {rel}:{n}\n      {line}")
    # The guarded set is DERIVED, so the remedy prints the derivation rather than a second
    # hand-list — the first one drifted four reads behind the KAL before anyone noticed.
    print("\nFix: call KNOWLEDGE_GATEWAY_URL /v1/kal/... instead of the owning "
          "service's /internal/* route.")
    print(f"The KAL federates these {len(KAL_COVERED_PATHS)} reads, derived from "
          f"{KAL_READ_CONTROLLER}:")
    for covered in KAL_COVERED_PATHS:
        print(f"    {covered}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
