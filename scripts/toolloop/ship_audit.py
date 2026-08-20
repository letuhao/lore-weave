#!/usr/bin/env python
"""The SHIP bar's two checks that the chat path cannot make: tenancy, and the absent case.

🔴 WHY THESE ARE NOT DRIVEN THROUGH THE MODEL. Every other bar in this loop insists on the real
chat path, because that is where 14 of 23 known defects live. Tenancy is the one place that rule
inverts: to make the model attack another user's book I would have to TYPE that book's id into the
prompt, and the LIVE bar says a typed argument voids the proof. Worse, it would test my ability to
phrase an attack rather than the tool's boundary.

So tenancy is checked where it actually lives — at the tool boundary, by calling the tool directly
as user A with a book owned by user B. No model, no phrasing, no ambiguity: either the tool refuses
or it does not.

The ABSENT case is different and does run through the chat path, because "the store is empty" is a
question about what the model reports, not about what the tool returns. That one is a scenario file
with the seed removed (see --empty), and its whole point is the failure this loop has already seen
twice: an answer of "you haven't declared any" over a populated table is the same sentence as a
truthful one over an empty table. Only the store can tell them apart, and only if BOTH cases are
run.

Usage:
    python scripts/toolloop/ship_audit.py --tenancy book_read,composition_list_outline
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from scripts.eval.tool_liveness import config as _tle_config  # noqa: E402
from scripts.eval.tool_liveness import oracle  # noqa: E402
from scripts.eval.tool_liveness.mcp_direct import MCPDirect  # noqa: E402

import catalog  # noqa: E402

#: The OTHER account. Its book is the thing the harness account must not be able to touch.
OTHER_USER = "019e97b0-f138-76f6-adf8-9253a8134770"  # claude-test2@loreweave.dev
TITLE_PREFIX = "LOOP-TENANCY-"
BOOK_DB = "loreweave_book"

#: A refusal has to be recognisable as one. Anything else — a result, an empty list, a 200 with
#: no rows — is a LEAK, because the caller learned something about a book they do not own.
REFUSAL_MARKERS = ("not accessible", "not found", "forbidden", "denied", "no access",
                   "unauthorized", "permission")

#: 🔴 A VALIDATION ERROR IS NOT A REFUSAL, AND IT FOOLED ME THREE TIMES.
#:
#: `glossary_entity_set_attributes` came back "entity_id must be a UUID";
#: `composition_outline_node_edit` came back "op=update requires project_id, node_id, and
#: expected_version"; `glossary_ontology_upsert` came back "validating /properties/items".
#: Every one of those is the schema rejecting my placeholder BEFORE the ownership check ran, so
#: the tenancy boundary was never exercised — and each one looked like a pass in a report that
#: only asked "did it fail?".
#:
#: The tell is in the message, so it is checkable: these strings mean the call died in
#: validation, and the correct verdict is UNPROBED, not refused. Fix the arguments from the
#: schema and probe again — every one of them, once given valid arguments, refused on ownership
#: with the store verified unchanged.
VALIDATION_MARKERS = ("validating", "must be a uuid", "is required", "required:", "invalid input",
                      "unexpected additional properties", "field required",
                      # Added 2026-08-14: memory_remember died on `fact_type`: "invalid arguments
                      # for memory_remember — `fact_type`: Input should be 'decision', …" and was
                      # scored `refused_other`, which is summarised alongside refusals in a line
                      # reading "0 LEAK(S)". A marker list that misses a phrasing turns a call
                      # that never reached the ownership check into a pass — the fifth time this
                      # family of false pass has been found in this instrument.
                      "invalid arguments for", "invalid arguments:", "value error", "input should be", "is not a valid",
                      "value is not a valid", "does not match",
                      # Business-level argument checks that still run BEFORE ownership. A tool
                      # that refuses an empty list has not yet looked at whose book it is, so
                      # scoring it `refused` would be the same false pass one layer up.
                      "must not be empty", "cannot be empty", "at least one")


def _placeholder(spec: dict):
    """A value the SCHEMA will accept, so the call reaches the ownership check.

    🔴 A BARE "x" DIES IN VALIDATION ON ANY ENUM, AND THAT READ AS A PASS. memory_remember
    requires `fact_type`, a closed enum; the probe sent "x", the call was rejected before
    ownership ran, and the verdict came back `refused_other` — indistinguishable, in the summary
    line, from a boundary that held. Read the enum the tool declares rather than guessing a
    string; the schema is right there.
    """
    enum = spec.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    t = spec.get("type")
    # 🔴 `type` CAN BE A UNION LIST, AND A BARE `t == "array"` MISSES IT. glossary_propose_batch
    # declares `ops` as `type: ["null", "array"]`; the probe compared against the LIST, fell
    # through to "x", died in validation and was reported UNPROBED. Take the first non-null
    # member — the same trap already recorded for an under-counting trigger that retired a real
    # catalogue member.
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), None)
    # 🔴 `type` IS OFTEN ABSENT WHERE THE SHAPE IS OBVIOUS, AND THE FALLBACK WAS "x".
    # glossary_propose_batch declares `ops` with `items` and NO `type`, so the probe sent the
    # string "x", died in validation, and was reported UNPROBED — the third time this instrument
    # has turned a call that never reached the ownership check into something that reads like a
    # result. Infer from the KEYS the schema does carry, in the order JSON Schema itself implies.
    if t is None:
        if "items" in spec:
            t = "array"
        elif "properties" in spec:
            t = "object"
        elif isinstance(spec.get("anyOf"), list):
            for alt in spec["anyOf"]:
                if isinstance(alt, dict) and alt.get("type") not in (None, "null"):
                    return _placeholder(alt)
    if t == "array":
        return []
    if t == "object":
        return {}
    if t in ("integer", "number"):
        return 1
    if t == "boolean":
        return False
    return "x"


def make_other_users_book() -> str:
    """A real book owned by the OTHER account.

    Inserted directly rather than through the API because the harness has no credential for that
    account, and seeding one would put a second password on disk for no benefit. The row is what
    matters: the tool resolves ownership from it.
    """
    bid = str(uuid.uuid4())
    title = f"{TITLE_PREFIX}{bid[:8]}"
    oracle.db_query(
        BOOK_DB,
        "INSERT INTO books (id, owner_user_id, title, original_language, lifecycle_state) "
        f"VALUES ('{bid}', '{OTHER_USER}', '{title}', 'en', 'active')")
    return bid


def drop_book(book_id: str) -> None:
    q = book_id.replace("'", "''")
    rows = oracle.db_query(BOOK_DB, f"SELECT title FROM books WHERE id='{q}'")
    if rows and rows[0] and str(rows[0][0]).startswith(TITLE_PREFIX):
        oracle.db_query(BOOK_DB, f"DELETE FROM chapters WHERE book_id='{q}'")
        oracle.db_query(BOOK_DB, f"DELETE FROM books WHERE id='{q}'")


KNOWLEDGE_DB = "loreweave_knowledge"


def make_other_users_project(book_id: str) -> str:
    """A real knowledge project owned by the OTHER account, on their book.

    🔴 WRITTEN WHERE THE TOOL ACTUALLY READS, AND THE FIRST VERSION WAS NOT. That version
    inserted into `loreweave_composition.composition_work`, and all three project-scoped tools
    came back `refused` with "project not found" — reported as 0 LEAKS. The control killed it:
    the SAME message comes back for a project id that does not exist anywhere
    (00000000-0000-4000-8000-000000000000), while a project the harness user owns returns
    `{"found": false}`. knowledge-service resolves ownership from its OWN `knowledge_projects`
    table, so the row was invisible to it and the boundary was never exercised. A probe that
    dies before the check reads exactly like a check that passed — the same failure the
    UNPROBED verdict was added for, one layer further down.

    🔴 A BOOK-ONLY PROBE CANNOT REACH A PROJECT-SCOPED TOOL, AND IT REPORTED THAT AS `n/a`.
    Measured 2026-08-14: `memory_recall_entity` declares `project_id` and no `book_id`, so the
    probe answered "its tenancy boundary is not the book" and moved on — truthful about the book
    and silent about the boundary the tool actually has. An unprobed boundary reported as `n/a`
    reads, in a batch summary of "0 LEAKS", exactly like a boundary that held.

    Roughly a fifth of the release surface is project-scoped (the memory and kg families,
    story_search), so this is the difference between auditing them and skipping them.

    Inserted directly for the same reason as the book: the harness holds no credential for that
    account, and the row is what ownership resolves from.
    """
    pid = str(uuid.uuid4())
    oracle.db_query(
        KNOWLEDGE_DB,
        "INSERT INTO knowledge_projects (project_id, user_id, name, project_type, book_id) "
        f"VALUES ('{pid}', '{OTHER_USER}', '{TITLE_PREFIX}tenancy', 'book', '{book_id}')")
    return pid


def make_other_users_map(book_db_owner: str = OTHER_USER) -> tuple[str, str]:
    """A world + map owned by the OTHER account, inserted directly for the same reason the book is.

    Worlds live in the BOOK database (`worlds`, `world_maps`), both carrying owner_user_id, so the
    map tools resolve ownership from these rows.
    """
    wid, mid = str(uuid.uuid4()), str(uuid.uuid4())
    oracle.db_query(
        BOOK_DB,
        "INSERT INTO worlds (id, owner_user_id, name) "
        f"VALUES ('{wid}', '{book_db_owner}', '{TITLE_PREFIX}tenancy-world')")
    oracle.db_query(
        BOOK_DB,
        "INSERT INTO world_maps (id, owner_user_id, world_id, name) "
        f"VALUES ('{mid}', '{book_db_owner}', '{wid}', '{TITLE_PREFIX}tenancy-map')")
    return wid, mid


def drop_map(world_id: str, map_id: str) -> None:
    """Name-guarded, like every other teardown here."""
    for tbl, col, ident in (("world_maps", "name", map_id), ("worlds", "name", world_id)):
        q = ident.replace("'", "''")
        rows = oracle.db_query(BOOK_DB, f"SELECT {col} FROM {tbl} WHERE id='{q}'")
        if rows and rows[0] and str(rows[0][0]).startswith(TITLE_PREFIX):
            oracle.db_query(BOOK_DB, f"DELETE FROM {tbl} WHERE id='{q}'")


def drop_project(project_id: str) -> None:
    """Name-guarded like drop_book: only ever removes a row this probe created."""
    q = project_id.replace("'", "''")
    rows = oracle.db_query(KNOWLEDGE_DB,
                           f"SELECT name FROM knowledge_projects WHERE project_id='{q}'")
    if rows and rows[0] and str(rows[0][0]).startswith(TITLE_PREFIX):
        oracle.db_query(KNOWLEDGE_DB, f"DELETE FROM knowledge_projects WHERE project_id='{q}'")


def probe(tool: str, book_id: str, cat: dict, project_id: str | None = None,
          map_id: str | None = None, world_id: str | None = None) -> dict:
    """Call `tool` as the harness user against another user's book OR project. Refusal is the pass.

    The scope is chosen from what the tool DECLARES, never guessed: a tool naming `book_id` is
    probed at the book, one naming only `project_id` is probed at the project. A tool naming
    neither has no tenancy argument at all and is the only honest `n/a`.
    """
    schema = (cat.get(tool) or {}).get("inputSchema") or {}
    props = set((schema.get("properties") or {}).keys())
    required = list(schema.get("required") or [])
    if "book_id" not in props and "project_id" in props and project_id:
        args = {"project_id": project_id}
        for r in required:
            if r == "project_id":
                continue
            spec = (schema.get("properties") or {}).get(r) or {}
            args[r] = _placeholder(spec)
        return _call_and_judge(tool, args)
    if "book_id" not in props and "world_id" in props and world_id:
        # The FOURTH scope. world_map_create carries only world_id, so it read as `n/a` while the
        # probe was already creating a world owned by the other account for the map arm below —
        # the fixture existed and simply was not handed over.
        args = {"world_id": world_id}
        for r in required:
            if r == "world_id":
                continue
            args[r] = _placeholder((schema.get("properties") or {}).get(r) or {})
        return _call_and_judge(tool, args)
    if "book_id" not in props and "map_id" in props and map_id:
        # 🔴 A THIRD SCOPE, AND WITHOUT IT THE MAP TOOLS READ AS `n/a`. world_map_add_marker and
        # world_map_add_region carry neither book_id nor project_id: their tenancy boundary is the
        # MAP. Reported as "no tenancy argument", they were counted alongside real refusals in a
        # line saying 0 LEAKS, which is the same false pass this file has now been corrected for
        # four times at four different scopes.
        args = {"map_id": map_id}
        for r in required:
            if r == "map_id":
                continue
            args[r] = _placeholder((schema.get("properties") or {}).get(r) or {})
        # A region needs a real polygon or it dies in the shape check before ownership runs.
        if "polygon" in required:
            args["polygon"] = [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]]
        for r in ("x", "y"):
            if r in required:
                args[r] = 0.1
        return _call_and_judge(tool, args)
    if "book_id" not in props:
        return {"tool": tool, "verdict": "n/a",
                "why": "declares no book_id, project_id, map_id or world_id — no tenancy argument"}
    args = {"book_id": book_id}
    # Fill any other required scalar with a placeholder so the call reaches the ownership check
    # rather than dying in validation — a validation error is not a refusal and must not be
    # scored as one.
    for r in required:
        if r == "book_id":
            continue
        spec = (schema.get("properties") or {}).get(r) or {}
        args[r] = "en" if r == "original_language" else _placeholder(spec)
    return _call_and_judge(tool, args)


def _call_and_judge(tool: str, args: dict) -> dict:
    """One verdict rule for both scopes — two copies would drift and one would quietly pass."""
    try:
        res = MCPDirect().call(tool, args)
        text = json.dumps(res).lower()
        leaked = not any(m in text for m in REFUSAL_MARKERS)
        return {"tool": tool, "args": args,
                "verdict": "LEAK" if leaked else "refused",
                "response": json.dumps(res)[:300]}
    except Exception as e:  # noqa: BLE001 — an MCPToolError IS the refusal on this path
        msg = str(e)
        low = msg.lower()
        if any(m in low for m in VALIDATION_MARKERS) and not any(m in low for m in REFUSAL_MARKERS):
            # The schema rejected the call before ownership ran, so the boundary was never
            # exercised. NOT a pass — and it read as one three times before this existed.
            return {"tool": tool, "args": args, "verdict": "UNPROBED (validation)",
                    "why": "died in argument validation, so the tenancy check never ran — fix "
                           "the args from the schema and probe again",
                    "response": msg[:300]}
        return {"tool": tool, "args": args,
                "verdict": "refused" if any(m in low for m in REFUSAL_MARKERS) else "refused_other",
                "response": msg[:300]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenancy", required=True, help="comma-separated tool names")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    cat = catalog.load()
    book = make_other_users_book()
    project = make_other_users_project(book)
    world, omap = make_other_users_map()
    print(f"other user's book: {book} (owner {OTHER_USER})")
    print(f"other user's project: {project}")
    print(f"other user's map: {omap}")
    out = []
    try:
        for t in [x.strip() for x in a.tenancy.split(",") if x.strip()]:
            r = probe(t, book, cat, project, omap, world)
            out.append(r)
            print(f"  {r['verdict']:<14} {t}  {r.get('response', '')[:110]}")
    finally:
        drop_map(world, omap)
        drop_project(project)
        drop_book(book)
    leaks = [r for r in out if r["verdict"] == "LEAK"]
    unprobed = [r for r in out if str(r["verdict"]).startswith("UNPROBED")]
    na = [r for r in out if r["verdict"] == "n/a"]
    if na:
        # `n/a` used to absorb every project-scoped tool and read like a pass in the summary line.
        print("\n   n/a is NOT a pass either — these declare no tenancy argument this probe "
              "can drive:")
        for r in na:
            print(f"     {r['tool']}: {r.get('why', '')}")
    if unprobed:
        print("\n   UNPROBED is NOT a pass — these died in validation before the ownership "
              "check ran:")
        for r in unprobed:
            print(f"     {r['tool']}")
    print(f"\n{len(out)} probed, {len(leaks)} LEAK(S)")
    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    return 1 if leaks else 0


if __name__ == "__main__":
    sys.exit(main())
