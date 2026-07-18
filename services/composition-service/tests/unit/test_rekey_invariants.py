"""Book-package re-key invariant guards (spec 25) — rule + SoT + gate + TEST.

Two pure-python lints (no DB, fast) that lock the Stage-1 re-key's two load-bearing
laws so a later edit can't silently undo them:

  a. The ACTOR is never a filter (PM-3 / PM-8 / DA-11). READ methods key on the
     package scope (project_id / book_id) and access is decided BEFORE the repo at
     the E0 book-grant gate; `created_by` is a STORED actor stamp that nothing ever
     filters on. A `created_by = $N` (or a surviving pre-rename `user_id = $N`)
     bound-parameter predicate in a re-keyed repo re-introduces the per-user filter
     the re-key deleted — the exact tenancy regression this guard fails on.

  b. PM-15 settings inventory. `composition_work.settings` is a SHARED per-book
     manifest, so every key the codebase writes/reads on it must be a package-tier
     PIN, never a per-user preference (settings-and-config SET-1..8). package_rekey's
     M0.5 only LOGS the live keys and its comment says the registry cross-check
     "lives in tests" — this is that cross-check.

Neither test touches a DB (no `xdist_group` mark).
"""

from __future__ import annotations

import re
from pathlib import Path

# tests/unit/test_rekey_invariants.py → .../composition-service
SERVICE_ROOT = Path(__file__).resolve().parents[2]
REPOS = SERVICE_ROOT / "app" / "db" / "repositories"
ROUTERS = SERVICE_ROOT / "app" / "routers"
CONFORMANCE = ROUTERS / "conformance.py"


# ── Guard 2a — the actor is NEVER a filter (PM-3 / PM-8 / DA-11) ──────────────

# A bound-parameter predicate ON THE ACTOR. `$\d` (a bound param) is the tell that
# this is a WHERE/AND filter, not an INSERT column list / VALUES / ON CONFLICT DO
# UPDATE SET created_by = EXCLUDED.created_by — none of those are `= $N`.
_CREATED_BY_FILTER = re.compile(r"created_by\s*=\s*\$\d")
# The pre-rename actor column. The leading lookbehind excludes `owner_user_id`
# (a DISTINCT scope key on the deps/ registry tables — NOT the actor).
_USER_ID_FILTER = re.compile(r"(?<![A-Za-z0-9_])user_id\s*=\s*\$\d")

# UNTOUCHED BY DESIGN (spec 25 PM-16): these repos back the deps/ registry
# (motif · arc_template · structure_template) and the outside-the-package /
# per-user tables — they KEEP owner_user_id / per-user `user_id` scope filters,
# which are legit SCOPE keys, not the demoted actor. Excluded from the `user_id`
# leftover check only (the `created_by = $N` law still applies to every file —
# `created_by` is only ever an actor stamp, nowhere a scope column).
UNTOUCHED_BY_DESIGN = {
    "daily_progress.py",       # composition_daily_progress / _baseline — per-user (PM-16)
    "import_source_repo.py",   # import_source — outside the package
    "consumed_tokens.py",      # consumed_tokens — outside the package
    "outbox.py",               # outbox_events — outside the package
    "arc_template_repo.py",    # arc_template — deps/ registry
    "structure_templates.py",  # structure_template — deps/ registry
    "motif_repo.py",           # motif — deps/ registry
    "motif_retrieve.py",       # motif — deps/ registry
}


def _actor_scan_files() -> list[Path]:
    """Every repository plus the conformance router (its INSERT/SELECT touch the
    re-keyed tables directly)."""
    return sorted(REPOS.glob("*.py")) + [CONFORMANCE]


def _lineno(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _line_at(text: str, pos: int) -> str:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return text[start : end if end != -1 else len(text)].strip()


def _find(pattern: re.Pattern[str], files: list[Path]) -> list[str]:
    hits: list[str] = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        for m in pattern.finditer(text):
            hits.append(f"{f.name}:{_lineno(text, m.start())}: {_line_at(text, m.start())}")
    return hits


def test_created_by_is_never_a_filter():
    """PM-3/PM-8/DA-11: `created_by` is a STORED actor stamp; access is the E0 book
    gate BEFORE the repo. A `created_by = $N` predicate anywhere in a re-keyed repo
    (or the conformance router) is a tenancy regression — the per-user filter the
    re-key removed, re-introduced under the new column name."""
    offenders = _find(_CREATED_BY_FILTER, _actor_scan_files())
    assert not offenders, (
        "spec 25 PM-3/PM-8 (DA-11): the actor `created_by` is STORED, NEVER filtered "
        "on — reads key on project_id/book_id and access is decided at the E0 book "
        "gate. Remove these `created_by = $N` predicates:\n  " + "\n  ".join(offenders)
    )


def test_no_user_id_actor_filter_survives():
    """PM-5: the actor column `user_id` was renamed to `created_by` on every package
    table; a surviving `user_id = $N` bound predicate in a re-keyed repo is an
    un-migrated per-user filter. (UNTOUCHED_BY_DESIGN keeps legit per-user/registry
    scope keys; `owner_user_id` is excluded by the regex lookbehind.)"""
    files = [f for f in _actor_scan_files() if f.name not in UNTOUCHED_BY_DESIGN]
    offenders = _find(_USER_ID_FILTER, files)
    assert not offenders, (
        "spec 25 PM-5: `user_id` is the pre-rename actor column and must not filter "
        "in a re-keyed repo (it became the stored `created_by` stamp). Offenders:\n  "
        + "\n  ".join(offenders)
    )


def test_actor_filter_regexes_are_live_gates():
    """Negative controls — a lint that cannot fail is not a gate. The regexes MUST
    fire on a real actor-filter predicate and MUST NOT fire on the benign
    INSERT/VALUES/ON-CONFLICT/SELECT shapes the re-key legitimately keeps."""
    # Positive: a genuine actor filter is caught.
    assert _CREATED_BY_FILTER.search("WHERE created_by = $1")
    assert _USER_ID_FILTER.search("WHERE user_id = $2")
    assert _USER_ID_FILTER.search("AND d.user_id = $1")
    # Negative: the stored-actor shapes are NOT filters.
    assert not _CREATED_BY_FILTER.search("SET created_by = EXCLUDED.created_by")
    assert not _CREATED_BY_FILTER.search("INSERT INTO t (created_by, project_id) VALUES ($1, $2)")
    assert not _CREATED_BY_FILTER.search("SELECT id, created_by, project_id FROM t")
    # Negative: owner_user_id is a DISTINCT scope key, not the actor.
    assert not _USER_ID_FILTER.search("WHERE owner_user_id = $1")


# ── Guard 2b — PM-15 settings inventory (SET-1..8) ────────────────────────────

# The CLOSED set of Book-tier keys allowed on the shared `composition_work.settings`
# manifest. Verified against the LIVE dev DB by M0.5's inventory on 2026-07-10 — which
# reported EIGHT keys where this code scan finds three. A scan of current write sites
# cannot see keys written by earlier schema versions, so this list is the contract and
# the scan is only one of its two inputs (`debt-batches-list-is-stale-verify-first`).
#
# PM-15's test is "would two users want different values?". For each key the answer is NO,
# because a user's own choice lives in a HIGHER tier of an existing cascade: the model keys
# are the **Book tier** of `System → Account → Book → Session`
# (docs/specs/2026-07-05-chat-ai-settings.md §3.2; routers/internal_model_settings.py), the
# drafter model is a REQUIRED per-call `model_ref` arg, and the rest are properties of the
# book. The re-key REMOVES a cross-tenant seam here: the Book tier used to be the owner's
# per-user Work row that a grantee had to reach across.
PACKAGE_TIER_SETTINGS = {
    "source_language",               # OQ-7 — the book's original language
    "reference_embed_model_ref",     # OQ-9 — one embedding space per Work (a technical pin)
    "reference_embed_model_source",  # OQ-9 — its provider kind
    "model_roles",                   # Book tier of the model cascade (the new map form)
    "default_model_ref",             # Book tier, legacy scalar → chat role; per-call model_ref wins
    "critic_model_ref",              # Book tier, legacy scalar → critic role
    "critic_model_source",           # its provider kind
    "assembly_mode",                 # how the book's prose assembles — a book property
    "narrative_thread_enabled",      # the book's promise-ledger toggle — steers shared generation
    "derivative_name",               # BE-13a — the dị bản's human label. Package-tier, not a
                                     # preference: it NAMES the derivative Work itself (seeded at
                                     # create in routers/works.py, read back as `name` by the MCP
                                     # work reads), so two grantees cannot want different values
                                     # for the same object the way they could a font size.
}

# The files that write/read `composition_work.settings` (the Work manifest).
_MANIFEST_SOURCES = (
    ROUTERS / "references.py",
    ROUTERS / "works.py",
    REPOS / "references.py",
)


def _read_manifest_sources() -> dict[str, str]:
    return {str(p.relative_to(SERVICE_ROOT)): p.read_text(encoding="utf-8") for p in _MANIFEST_SOURCES}


def _extract_manifest_setting_keys(sources: dict[str, str]) -> set[str]:
    """Discover every settings key the code writes to / reads from the Work manifest:
      • `merged[KEY] = …`         — the write-through merge copy (references router)
      • `_init_settings = {…}` / `settings = {…}` dict-literal keys (works router)
      • `s.get(KEY)` / `settings.get(KEY)` — per-key reads (references repo)
    KEY is a quoted literal or an UPPER_SNAKE module constant (resolved via the
    `NAME = "literal"` assignments in the same files)."""
    const: dict[str, str] = {}
    for text in sources.values():
        for m in re.finditer(r'^([A-Z][A-Z0-9_]*)\s*=\s*["\']([^"\']+)["\']', text, re.M):
            const[m.group(1)] = m.group(2)

    def resolve(tok: str) -> str | None:
        tok = tok.strip()
        if len(tok) >= 2 and tok[0] in "\"'" and tok[-1] == tok[0]:
            return tok[1:-1]
        return const.get(tok)  # UPPER_SNAKE constant → its literal value; else unknown

    keys: set[str] = set()
    key_tok = r'([A-Z_][A-Z0-9_]*|"[^"]+"|\'[^\']+\')'
    for text in sources.values():
        for m in re.finditer(r"\bmerged\[\s*" + key_tok + r"\s*\]", text):
            if (k := resolve(m.group(1))) is not None:
                keys.add(k)
        for blk in re.finditer(r"(?:_init_settings|settings)\s*=\s*\{([^}]*)\}", text):
            keys.update(km.group(1) for km in re.finditer(r'["\']([^"\']+)["\']\s*:', blk.group(1)))
        for m in re.finditer(r"\b(?:s|settings)\.get\(\s*" + key_tok, text):
            if (k := resolve(m.group(1))) is not None:
                keys.add(k)
    return keys


def test_manifest_settings_are_package_tier_only():
    """PM-15 / SET-1..8: `composition_work.settings` is a SHARED per-book manifest,
    so a per-user key there is a tenancy defect (two collaborators would clobber each
    other's preference). Every key the code writes/reads on it must be an allowlisted
    package-tier pin."""
    keys = _extract_manifest_setting_keys(_read_manifest_sources())
    # A lint that finds nothing cannot fail — if the discovery drifts from the code,
    # fail loudly rather than pass vacuously.
    assert keys, (
        "settings-inventory discovery matched NO keys — the extractor regexes have "
        "drifted from the manifest write/read sites; re-derive them before trusting "
        "this gate."
    )
    extra = keys - PACKAGE_TIER_SETTINGS
    assert not extra, (
        "spec 25 PM-15 (settings-and-config SET-1..8): these keys are written to the "
        f"SHARED composition_work.settings manifest but are not package-tier pins: "
        f"{sorted(extra)}. A per-user preference belongs in the user-settings tier "
        "(/v1/me/preferences), never on the per-book manifest — else two grantees "
        "overwrite each other. If it IS a package-tier pin, add it to "
        "PACKAGE_TIER_SETTINGS with its spec-25 open-question decision."
    )


def test_settings_inventory_extractor_is_a_live_gate():
    """Negative control: the extractor MUST surface a would-be per-user key so the
    subset check above can actually fail on a real regression."""
    synthetic = {
        "synthetic.py": (
            'PER_USER_FONT = "reader_font_size"\n'
            "merged[PER_USER_FONT] = body.size\n"
            '_init_settings = {"per_user_theme": theme}\n'
            's.get("per_user_locale")\n'
        )
    }
    found = _extract_manifest_setting_keys(synthetic)
    assert {"reader_font_size", "per_user_theme", "per_user_locale"} <= found, found
    assert found - PACKAGE_TIER_SETTINGS, "the synthetic per-user keys must trip the subset check"


# ── Guard 2c — package_rekey DDL guards are SCHEMA-QUALIFIED (D-PKGREKEY-DDL-*) ──

PACKAGE_REKEY = SERVICE_ROOT / "app" / "db" / "package_rekey.py"

# An `information_schema.columns/constraint_column_usage` existence guard that omits a
# `table_schema` predicate can be satisfied by a SAME-NAMED table in ANOTHER schema —
# so the rekey's conditional DDL fires (or skips) off the wrong table. Every guard must
# scope to `current_schema()` (search-path-correct). Each guard is a `FROM
# information_schema.<view>` followed within a few lines by its WHERE clause.
_INFO_SCHEMA_GUARD = re.compile(
    r"FROM\s+information_schema\.\w+(?P<body>.*?)(?:\)\s*THEN|\)\s*\"\"\"|\)$)",
    re.S,
)


def test_package_rekey_information_schema_guards_are_schema_qualified():
    """D-PKGREKEY-DDL-SCHEMA-QUALIFIER: every information_schema existence guard in
    package_rekey.py must filter `table_schema` (→ current_schema()), or a same-named
    table in another schema could satisfy the guard and mis-fire the conditional DDL."""
    text = PACKAGE_REKEY.read_text(encoding="utf-8")
    guards = list(_INFO_SCHEMA_GUARD.finditer(text))
    # A lint that matches nothing is not a gate.
    assert len(guards) >= 8, (
        f"expected ≥8 information_schema guards in package_rekey.py, found {len(guards)} "
        "— the guard regex has drifted; re-derive it before trusting this test."
    )
    offenders = [
        f"L{_lineno(text, g.start())}: {_line_at(text, g.start())}"
        for g in guards
        if "table_schema" not in g.group("body")
    ]
    assert not offenders, (
        "D-PKGREKEY-DDL-SCHEMA-QUALIFIER: these information_schema guards omit a "
        "`table_schema = current_schema()` filter, so a same-named table in another "
        "schema could satisfy them and mis-fire the re-key DDL:\n  " + "\n  ".join(offenders)
    )


def test_info_schema_guard_regex_is_a_live_gate():
    """Negative control: the guard regex MUST flag an unqualified guard and MUST NOT
    flag a qualified one."""
    unq = ("IF EXISTS (SELECT 1 FROM information_schema.columns\n"
           "           WHERE table_name = 't' AND column_name = 'c') THEN")
    qual = ("IF EXISTS (SELECT 1 FROM information_schema.columns\n"
            "           WHERE table_name = 't' AND column_name = 'c'\n"
            "             AND table_schema = current_schema()) THEN")
    mu = _INFO_SCHEMA_GUARD.search(unq)
    mq = _INFO_SCHEMA_GUARD.search(qual)
    assert mu and "table_schema" not in mu.group("body")   # unqualified → offender
    assert mq and "table_schema" in mq.group("body")        # qualified → clean
