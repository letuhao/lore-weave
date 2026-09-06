#!/usr/bin/env python3
"""entity-lifecycle-outbox-gate — a lifecycle mutation must carry its event (plan T27).

WHAT WENT WRONG, FOUR TIMES
---------------------------
`softDeleteEntityCore`, `bulkDeleteEntities`, `restoreEntityCore` and `purgeEntity` each
mutated `glossary_entities`' lifecycle columns (`deleted_at`, `permanently_deleted_at`) and
emitted NOTHING. The downstream KG mirror therefore never learned about any of them, and the
machinery to act on it already existed, unused, because nothing told it. The restore half was
the worst: a deleted-then-restored entity stayed archived downstream forever, and no retry
converged it, because the corrective event did not exist.

None of that was a wrong UPDATE. It was an UPDATE written without its event, four separate
times, in four files, over months — which is a shape problem, and shape problems need a gate
rather than a reviewer's memory.

AND THEN TWICE MORE, ON A DIFFERENT AXIS (plan T28)
---------------------------------------------------
`bulkSetEntityStatusCore` and `reassignEntityKindCore` wrote `status` and `kind_id` and emitted
nothing either. `status` is not a label in this service — it is a LIVENESS predicate: every
consumer-facing read filters `status = 'active'` alongside `deleted_at IS NULL`. Retiring an
entity to `inactive` or `rejected` therefore removed it from the glossary's own canon reads
while the KG mirror kept the node and kept answering RAG queries about it. The same split
brain, reached by a different verb — which is why this gate now polices both axes.

WHAT THIS CHECKS
----------------
Every Go function in `services/glossary-service/internal/api` that writes a lifecycle column
(`deleted_at`, `permanently_deleted_at`) or a curation column (`status`, `kind_id`) of
`glossary_entities` must, in the same function, either emit an event or delegate to a helper
that does. The runtime twin of this check is the WARN in `mutateEntityLifecycleTx` and
`setEntityStatusCore` when an emit fails.

It is deliberately shallow: it does not try to prove the emit is in the same transaction —
that is what the `mutateEntityLifecycleTx`/`lifecycleEntityCore` helpers are for, and a gate
that tried to verify transactionality by reading source would be a parser pretending to be a
type system. What it catches is the absence, which is the failure that actually happened.

    python scripts/entity-lifecycle-outbox-gate.py

Exit 0 = clean · 1 = a silent lifecycle mutation · 2 = could not run.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "services" / "glossary-service" / "internal" / "api"

# A lifecycle write: setting deleted_at / permanently_deleted_at on glossary_entities.
_LIFECYCLE_SQL = re.compile(
    r"UPDATE\s+glossary_entities[\s\S]{0,400}?SET[\s\S]{0,400}?"
    r"(deleted_at\s*=\s*(now\(\)|NULL)|permanently_deleted_at\s*=\s*now\(\))",
    re.IGNORECASE,
)

# A curation write: setting status / kind_id on glossary_entities (plan T28).
#
# The `(?!UPDATE)` lookahead is why this pattern is not simply the lifecycle one with two more
# column names. Several functions run two statements in a row — `UPDATE glossary_entities SET
# deleted_at=NULL ...` followed by `UPDATE merge_journal SET status='reverted' ...` — and a
# plain 400-character window happily spans the gap, reporting the SECOND statement's `status`
# as a write to `glossary_entities`. The lookahead stops the scan at the next statement, so a
# match means the SET really does belong to the glossary_entities UPDATE that opened it.
#
# `kind_labels` deliberately does NOT match: it is a facet list, not the entity's kind, and the
# integrity-repair sweeper rewrites it without changing what the entity IS.
_CURATION_SQL = re.compile(
    r"UPDATE\s+glossary_entities(?:\s+\w+)?\s*(?:(?!UPDATE)[\s\S]){0,200}?SET"
    r"(?:(?!UPDATE)[\s\S]){0,400}?"
    r"\b(status|kind_id)\s*=",
    re.IGNORECASE,
)

# A MIRRORED-CONTENT write: the columns a consumer keeps a copy of (plan T29).
#
# `short_description` is the third instance of the same defect, found by asking which columns
# a consumer MIRRORS rather than which table is written. `regenerateAutoShortDescription` runs
# post-commit for two callers that had already emitted `entity_updated` INSIDE their
# transaction, so the mirror kept the pre-edit summary forever — in the one field the
# composition packer reads for a cast bio.
#
# `cached_name`/`cached_aliases` are trigger-maintained rather than hand-written today; they
# are listed because they are what `loadEntityEventFields` reads, so a future hand-write to
# either has the same consequence and should meet the same rule.
_MIRRORED_SQL = re.compile(
    r"UPDATE\s+glossary_entities(?:\s+\w+)?\s*(?:(?!UPDATE)[\s\S]){0,200}?SET"
    r"(?:(?!UPDATE)[\s\S]){0,500}?"
    r"\b(short_description|cached_name|cached_aliases)\s*=",
    re.IGNORECASE,
)

# Emitting, or delegating to something that does. `insertMergedOutboxEvent` and
# `emitEntityUpdated` count: a merge's soft-delete of the loser IS announced — as
# `glossary.entity_merged`, which knowledge-service already consumes to rewire the graph.
# The gate's question is "does this transition reach a consumer", not "does it use the
# lifecycle helper".
_EMITS = re.compile(
    r"emitEntityLifecycleTx|mutateEntityLifecycleTx|lifecycleEntityCore|"
    r"bulkDeleteEntitiesCore|purgeEntityCore|softDeleteEntityCore|restoreEntityCore|"
    r"insertMergedOutboxEvent|emitEntityUpdated|"
    # T28 — the curation axis. `setEntityStatusCore` is the one place a curated status write
    # lives; the two named entry points delegate to it, and `emitEntityStatusChangedTx` is the
    # emit itself. `insertEntityOutboxEvent` is the generic entity_updated writer used by the
    # kind-vote paths, which announce a re-kind with the RESOLVED kind in the payload.
    r"emitEntityStatusChangedTx|setEntityStatusCore|bulkSetEntityStatusCore|"
    r"reassignEntityKindCore|insertEntityOutboxEvent"
)

# Functions whose lifecycle write is announced by their CALLER. Each entry states which
# event covers it, because "a caller emits it" is a claim that rots: the day someone splits
# the caller, the exemption is still here and still silent.
#
# An entry that no longer matches a real finding is an ERROR, not a leftover — the same rule
# graph-port-gate uses. A stale exemption re-permits exactly the line it names the moment
# somebody reintroduces it.
# Each entry names the CALLERS that announce the transition, and the gate checks them. An
# exemption phrased as prose is a promise; an exemption that names its emitters is a claim the
# gate can keep. T28's second bite is why: removing the emit from `reassignEntityKindCore` left
# the gate green, because the SQL lives in the allowlisted `rekeyEntityToKind` and nothing ever
# looked at whether the caller the exemption pointed to still emitted. The exemption survived
# the disappearance of the exact thing that justified it.
ALLOWLIST = {
    "mergeOne": (
        "the loser's soft-delete is part of a merge, announced as glossary.entity_merged + "
        "entity_updated for both sides",
        ("mergeEntitiesCore",),
    ),
    # T28 — three internals that hold the SQL for a transition their caller announces. Each is
    # a private helper with a named, checked caller, which is the shape this gate wants: the
    # write and the emit in one transaction, expressed as one function pair.
    "rekeyEntityToKind": (
        "holds the re-key UPDATE; its only caller emits glossary.entity_updated carrying the "
        "NEW kind in the same transaction",
        ("reassignEntityKindCore",),
    ),
    # Named at the OUTERMOST function, not at `resolveEntityKind` — which is a pass-through
    # that returns the resolution precisely so its caller can emit the RESOLVED kind rather
    # than the proposed one. Naming the pass-through would have exempted this on a function
    # that has never emitted anything, which the verification caught on its first run.
    "applyKindResolution": (
        "writes the resolved kind for the vote paths; both entry points emit entity_updated "
        "with the RESOLVED kind, gated on `moved`",
        ("bulkExtractEntities", "internalImportKindVotes"),
    ),
    "regenerateAutoShortDescription": (
        "recomputes the auto summary for five callers; the three in-tx ones regenerate BEFORE "
        "their emit so the before/after snapshot captures it, and the two post-commit ones "
        "emit when it reports the summary actually moved",
        ("applyEntityEdit", "setEntityAttributes"),
    ),
    "reconcileEntityFromSnapshot": (
        "restores every column including status; its only caller emits entity_updated AND, "
        "since T28, entity_status_changed when the snapshot moves the status",
        ("restoreEntityRevisionCore",),
    ),
}

_FUNC = re.compile(r"^func\s+(?:\([^)]*\)\s*)?(\w+)\s*\(", re.MULTILINE)


def _strip_comments(src: str) -> str:
    """Blank Go comments, preserving offsets and every string literal.

    THE THIRD BITE THIS GATE FAILED, and the most embarrassing of the three. Removing the emit
    from `setEntityStatusCore` left the gate green, because the comment on the roll-back branch
    right below it explains the reasoning by NAMING `bulkDeleteEntitiesCore` — which is in
    `_EMITS`. A function that emits nothing passed because its prose mentioned a function that
    does. T27 hit the same class twice (a self-matching signature, then a neighbour's doc
    comment) and both fixes were about the chunk's BOUNDARIES; neither touched the fact that
    prose inside those boundaries counts as evidence. It does not, now.

    String literals are deliberately KEPT — the SQL this gate matches on lives in backtick raw
    strings, so blanking them the way the gateway domain-logic gate does would leave nothing to
    police and the "matched zero" guard would be the only thing standing.

    Offsets are preserved (comments become spaces, newlines survive) so reported line numbers
    still point at the real source.
    """
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == "`":  # raw string — runs to the next backtick, no escapes
            j = src.find("`", i + 1)
            i = n if j == -1 else j + 1
            continue
        if c == '"' or c == "'":  # interpreted string / rune — honours backslash escapes
            quote, j = c, i + 1
            while j < n and src[j] != quote:
                j += 2 if src[j] == "\\" else 1
            i = j + 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            j = n if j == -1 else j
            for k in range(i, j):
                out[k] = " "
            i = j
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            j = n if j == -1 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
            continue
        i += 1
    return "".join(out)


def _functions(text: str):
    """(name, body, line) per top-level func. Bodies run to the next top-level `func`, which
    is enough: gofmt guarantees a top-level func starts at column 0.

    The body EXCLUDES the declaration line, and that is load-bearing rather than tidy.
    `_EMITS` lists the `*Core` names so a handler that delegates to one counts as emitting —
    which also made every `*Core` function match its OWN signature. The first bite of this
    gate passed for exactly that reason: `restoreEntityCore` reverted to a silent
    `pool.Exec` still "emitted", because its name appeared in its own `func` line.
    """
    marks = [(m.start(), m.group(1)) for m in _FUNC.finditer(text)]
    for i, (start, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        chunk = text[start:end]
        # Trim to the function's OWN braces: from the first `{` to the closing `}` at column
        # 0. Without the tail trim the chunk swallows the doc comment of the NEXT function —
        # and the second bite of this gate passed because of exactly that: the comment above
        # `purgeEntityCore` sat inside `restoreEntityCore`'s chunk, and `purgeEntityCore` is
        # in `_EMITS`, so a silenced restore still looked like it emitted.
        open_brace = chunk.find("{")
        close = chunk.rfind("\n}")
        if open_brace == -1:
            continue
        body = chunk[open_brace:close] if close > open_brace else chunk[open_brace:]
        yield name, body, text[:start].count("\n") + 1


def main() -> int:
    if not API.is_dir():
        print(f"[entity-lifecycle-outbox-gate] FAIL(setup): {API} not found", file=sys.stderr)
        return 2

    # Every function in the package, so an allowlist entry's named emitters can be checked
    # wherever they live — the helper and the caller that announces it are routinely in
    # different files (rekeyEntityToKind/reassignEntityKindCore happen to share one; mergeOne
    # and reconcileEntityFromSnapshot do not).
    bodies: dict[str, str] = {}
    findings, checked, used_allow = [], 0, set()
    for path in sorted(API.glob("*.go")):
        if path.name.endswith("_test.go"):
            continue
        text = _strip_comments(path.read_text(encoding="utf-8"))
        for name, body, line in _functions(text):
            bodies[name] = body
            if "glossary_entities" not in text:
                continue
            if not (_LIFECYCLE_SQL.search(body)
                    or _CURATION_SQL.search(body)
                    or _MIRRORED_SQL.search(body)):
                continue
            checked += 1
            if _EMITS.search(body):
                continue
            if name in ALLOWLIST:
                used_allow.add(name)
                continue
            findings.append(
                (str(path.relative_to(ROOT)).replace("\\", "/"), line, name)
            )

    # Hold each USED exemption to the emitters it names. This is the half the second T28 bite
    # proved was missing: without it, deleting the emit from the caller an exemption points at
    # leaves the gate green, because the SQL sits in the exempted helper and nobody looks up.
    broken = []
    for name in sorted(used_allow):
        reason, emitters = ALLOWLIST[name]
        for emitter in emitters:
            if emitter not in bodies:
                broken.append((name, emitter, "no such function in the package"))
            elif not _EMITS.search(bodies[emitter]):
                broken.append((name, emitter, "no longer emits"))
    if broken:
        print("[entity-lifecycle-outbox-gate] FAIL — an exemption's emitter stopped emitting:")
        for name, emitter, why in broken:
            print(f"  {name}() is exempt because {emitter}() announces it — but {emitter}() {why}")
        print(
            "\n  The write is now silent and the allowlist is hiding it. Restore the emit in\n"
            "  the named function, or remove the exemption so the helper is policed directly.",
        )
        return 1

    stale = set(ALLOWLIST) - used_allow
    if stale:
        print("[entity-lifecycle-outbox-gate] FAIL — stale allowlist entry/entries:")
        for name in sorted(stale):
            print(f"  {name}() — {ALLOWLIST[name][0]}")
        print("\n  It no longer matches a lifecycle write. Remove it, or the exemption\n"
              "  silently re-permits that function the day it comes back.")
        return 1

    if not checked:
        # The gate found NO lifecycle mutation anywhere. That is not a pass — it means the
        # pattern stopped matching (a rename, a reformat) and this gate has been quietly
        # measuring nothing. The four call sites it was written for are still there.
        print(
            "[entity-lifecycle-outbox-gate] FAIL — matched zero lifecycle mutations.\n"
            "  The SQL pattern no longer finds the writes this gate exists to police,\n"
            "  so a pass would be meaningless. Fix the pattern, not this message.",
        )
        return 1

    if findings:
        print("[entity-lifecycle-outbox-gate] FAIL — entity transition with no event:")
        for file, line, name in findings:
            print(f"  {file}:{line}  {name}()")
        print(
            "\n  A transition that announces nothing leaves the KG mirror wrong with no way\n"
            "  to converge: a restored entity stays archived downstream forever (T27), and a\n"
            "  retired one keeps answering RAG queries after every glossary read has dropped\n"
            "  it (T28 — `status` is a liveness predicate here, not a label).\n"
            "\n  Route a delete/restore/purge through mutateEntityLifecycleTx, a status change\n"
            "  through setEntityStatusCore, and a re-key through reassignEntityKindCore.",
        )
        return 1

    print(
        f"[entity-lifecycle-outbox-gate] PASS — {checked} lifecycle mutation(s), all emit"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
