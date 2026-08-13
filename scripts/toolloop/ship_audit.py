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


def probe(tool: str, book_id: str, cat: dict) -> dict:
    """Call `tool` as the harness user against another user's book. Refusal is the pass."""
    schema = (cat.get(tool) or {}).get("inputSchema") or {}
    props = set((schema.get("properties") or {}).keys())
    required = list(schema.get("required") or [])
    if "book_id" not in props:
        return {"tool": tool, "verdict": "n/a",
                "why": "declares no book_id — its tenancy boundary is not the book"}
    args = {"book_id": book_id}
    # Fill any other required scalar with a placeholder so the call reaches the ownership check
    # rather than dying in validation — a validation error is not a refusal and must not be
    # scored as one.
    for r in required:
        if r == "book_id":
            continue
        spec = (schema.get("properties") or {}).get(r) or {}
        t = spec.get("type")
        args[r] = "en" if r == "original_language" else ("x" if t in (None, "string") else 1)
    try:
        res = MCPDirect().call(tool, args)
        text = json.dumps(res).lower()
        leaked = not any(m in text for m in REFUSAL_MARKERS)
        return {"tool": tool, "args": args,
                "verdict": "LEAK" if leaked else "refused",
                "response": json.dumps(res)[:300]}
    except Exception as e:  # noqa: BLE001 — an MCPToolError IS the refusal on this path
        msg = str(e)
        return {"tool": tool, "args": args,
                "verdict": "refused" if any(m in msg.lower() for m in REFUSAL_MARKERS)
                           else "refused_other",
                "response": msg[:300]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenancy", required=True, help="comma-separated tool names")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    cat = catalog.load()
    book = make_other_users_book()
    print(f"other user's book: {book} (owner {OTHER_USER})")
    out = []
    try:
        for t in [x.strip() for x in a.tenancy.split(",") if x.strip()]:
            r = probe(t, book, cat)
            out.append(r)
            print(f"  {r['verdict']:<14} {t}  {r.get('response', '')[:110]}")
    finally:
        drop_book(book)
    leaks = [r for r in out if r["verdict"] == "LEAK"]
    print(f"\n{len(out)} probed, {len(leaks)} LEAK(S)")
    if a.out:
        pathlib.Path(a.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    return 1 if leaks else 0


if __name__ == "__main__":
    sys.exit(main())
