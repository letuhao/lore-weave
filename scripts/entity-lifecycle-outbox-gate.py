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

WHAT THIS CHECKS
----------------
Every Go function in `services/glossary-service/internal/api` that writes a lifecycle column
of `glossary_entities` must, in the same function, either emit a lifecycle event or delegate
to a helper that does. The runtime twin of this check is the WARN in
`mutateEntityLifecycleTx` when an emit fails.

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

# Emitting, or delegating to something that does. `insertMergedOutboxEvent` and
# `emitEntityUpdated` count: a merge's soft-delete of the loser IS announced — as
# `glossary.entity_merged`, which knowledge-service already consumes to rewire the graph.
# The gate's question is "does this transition reach a consumer", not "does it use the
# lifecycle helper".
_EMITS = re.compile(
    r"emitEntityLifecycleTx|mutateEntityLifecycleTx|lifecycleEntityCore|"
    r"bulkDeleteEntitiesCore|purgeEntityCore|softDeleteEntityCore|restoreEntityCore|"
    r"insertMergedOutboxEvent|emitEntityUpdated"
)

# Functions whose lifecycle write is announced by their CALLER. Each entry states which
# event covers it, because "a caller emits it" is a claim that rots: the day someone splits
# the caller, the exemption is still here and still silent.
#
# An entry that no longer matches a real finding is an ERROR, not a leftover — the same rule
# graph-port-gate uses. A stale exemption re-permits exactly the line it names the moment
# somebody reintroduces it.
ALLOWLIST = {
    "mergeOne": (
        "the loser's soft-delete is part of a merge; mergeEntitiesCore (its only caller) "
        "emits glossary.entity_merged + entity_updated for both sides"
    ),
}

_FUNC = re.compile(r"^func\s+(?:\([^)]*\)\s*)?(\w+)\s*\(", re.MULTILINE)


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

    findings, checked, used_allow = [], 0, set()
    for path in sorted(API.glob("*.go")):
        if path.name.endswith("_test.go"):
            continue
        text = path.read_text(encoding="utf-8")
        if "glossary_entities" not in text:
            continue
        for name, body, line in _functions(text):
            if not _LIFECYCLE_SQL.search(body):
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

    stale = set(ALLOWLIST) - used_allow
    if stale:
        print("[entity-lifecycle-outbox-gate] FAIL — stale allowlist entry/entries:")
        for name in sorted(stale):
            print(f"  {name}() — {ALLOWLIST[name]}")
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
        print("[entity-lifecycle-outbox-gate] FAIL — lifecycle mutation with no event:")
        for file, line, name in findings:
            print(f"  {file}:{line}  {name}()")
        print(
            "\n  A delete/restore/purge that announces nothing leaves the KG mirror wrong\n"
            "  with no way to converge — a restored entity stays archived downstream\n"
            "  forever. Route the write through lifecycleEntityCore (plan T27).",
        )
        return 1

    print(
        f"[entity-lifecycle-outbox-gate] PASS — {checked} lifecycle mutation(s), all emit"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
