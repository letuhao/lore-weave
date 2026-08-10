#!/usr/bin/env python3
"""CP-6.1 · replay the REAL `unknown kind` failures through the vocabulary resolver.

    python scripts/cp6-vocabulary-replay.py

Read-only. Every denominator is a query result.

🔴 **THE RULE THIS EXISTS FOR (W2, and CP-5.3 paid for it twice).** A mechanism measured on a
convenient population tells you nothing about the population it is for. So the input here is
**derived from the failures themselves** -- every recorded `glossary_propose_entities` call whose
error says `unknown kind` -- and each one is replayed against the LIVE ontology of its OWN book and
the LIVE system standards.

What it reports, per call:

* `refused`   -- the resolver would have stopped this call before the wire, naming the book's kinds
* `adoptable` -- of those, how many name a STANDARD kind that is one adoption call away
* `would_pass`-- the kind IS in the book's ontology today, so the resolver would NOT have refused.
                 This is the number that could embarrass the design and is printed first: it means
                 the ontology changed after the failure, so the refusal would have been wrong.
* `no_book`   -- the book or its ontology is gone; unmeasurable, counted apart and never folded in.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "chat-service"))

from app.agentruntime.vocabulary import (  # noqa: E402
    Pending, decide, load_registry,
)

PG = os.environ.get("CP5_PG_CONTAINER", "infra-postgres-1")
REGISTRY = ROOT / "contracts" / "agent-runtime-vocabularies.json"


def psql(db: str, sql: str) -> str:
    p = subprocess.run(
        ["docker", "exec", PG, "psql", "-U", "loreweave", "-d", db, "-At", "-F", "\x1f", "-c", sql],
        capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise SystemExit(f"psql {db}: {p.stderr.strip()}")
    return p.stdout


FAILING_SQL = """
SELECT m.session_id, tc->'args'->>'book_id', tc->'args'->>'items'
FROM chat_messages m, LATERAL jsonb_array_elements(m.tool_calls) tc
WHERE tc->>'tool' = 'glossary_propose_entities'
  AND tc->>'error' ILIKE '%unknown kind%'
"""


def book_kinds(book_id: str) -> list[dict] | None:
    """THIS book's adopted kinds, live. `None` when the book has no ontology rows at all."""
    out = psql("loreweave_glossary",
               f"SELECT code FROM book_kinds WHERE book_id = '{book_id}'")
    codes = [c.strip() for c in out.splitlines() if c.strip()]
    return [{"code": c} for c in codes] if codes else None


def system_standards() -> list[dict]:
    out = psql("loreweave_glossary", "SELECT code FROM system_kinds")
    return [{"code": c.strip()} for c in out.splitlines() if c.strip()]


def main() -> int:
    doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
    # Every source in this registry is a READ; the replay asserts that rather than assuming it, so
    # a registry edit that made a source a write would fail HERE too and not only in the service.
    vocabs, bindings = load_registry(doc, lambda t: "read")
    standards = {"kinds": system_standards()}
    print(f"system standards: {len(standards['kinds'])} kinds")

    rows = [r.split("\x1f") for r in psql("loreweave_chat", FAILING_SQL).splitlines() if r.strip()]
    print(f"population (DERIVED FROM THE FAILURES): {len(rows)} calls\n")

    counts = {"refused": 0, "would_pass": 0, "no_book": 0, "no_kinds_sent": 0}
    adoptable_calls = 0
    adoptable_values: dict[str, int] = {}
    custom_values: dict[str, int] = {}
    sample = []
    seen_books: dict[str, list[dict] | None] = {}

    for _session, book_id, items_json in rows:
        if not book_id:
            counts["no_book"] += 1
            continue
        if book_id not in seen_books:
            seen_books[book_id] = book_kinds(book_id)
        kinds = seen_books[book_id]
        if kinds is None:
            counts["no_book"] += 1
            continue
        try:
            items = json.loads(items_json) if items_json else []
        except json.JSONDecodeError:
            items = []
        call_args = {"book_id": book_id, "items": items}
        pendings = [
            Pending(tool=t, param=p, vocabulary=vocabs[v],
                    sent=tuple(dict.fromkeys(
                        x.strip() for it in (items or []) if isinstance(it, dict)
                        for x in [it.get("kind")] if isinstance(x, str) and x.strip())),
                    source_args={"book_id": book_id})
            for (t, p), v in bindings.items() if t == "glossary_propose_entities"
        ]
        pendings = [pd for pd in pendings if pd.sent]
        if not pendings:
            counts["no_kinds_sent"] += 1
            continue
        for pd in pendings:
            d = decide(pd, {"ontology": {"kinds": kinds}}, standards)
            if d.is_ok:
                counts["would_pass"] += 1
                continue
            counts["refused"] += 1
            if d.adoptable:
                adoptable_calls += 1
            for a in d.adoptable:
                adoptable_values[a] = adoptable_values.get(a, 0) + 1
            for c in d.custom:
                custom_values[c] = custom_values.get(c, 0) + 1
            if len(sample) < 3:
                from app.agentruntime.vocabulary import refusal_message
                sample.append(refusal_message([d]))

    measurable = counts["refused"] + counts["would_pass"]
    print("REPLAY")
    print(f"  refused before the wire   {counts['refused']:>4}")
    print(f"  would PASS today          {counts['would_pass']:>4}   "
          f"(the ontology gained the kind after the failure; a refusal here would be WRONG)")
    print(f"  unmeasurable (no book)    {counts['no_book']:>4}")
    print(f"  no kind sent at all       {counts['no_kinds_sent']:>4}")
    if measurable:
        print(f"\n  of {measurable} measurable calls, {counts['refused'] / measurable * 100:.1f}% "
              f"would be refused before the wire")
        print(f"  of {counts['refused']} refusals, {adoptable_calls} "
              f"({adoptable_calls / counts['refused'] * 100:.1f}%) name at least one ADOPTABLE "
              f"standard kind — one call away")
    print(f"\n  adoptable values: {sorted(adoptable_values.items(), key=lambda x: -x[1])}")
    print(f"  custom values   : {sorted(custom_values.items(), key=lambda x: -x[1])[:12]}")
    for s in sample:
        print(f"\n  SAMPLE REFUSAL: {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
