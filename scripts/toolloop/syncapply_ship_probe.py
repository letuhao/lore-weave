"""SHIP audit for glossary_book_sync_apply — gate / empty / absent / tenancy.

The divergence is seeded PER BOOK, on the throwaway's own book_kinds rows, exactly as the
scenario's seed does: source_hash is the BOOK's record of what it adopted, so staling it makes
the upstream row differ without touching any shared standard. Verified on a throwaway: updates
went [] -> rows, and teardown left none.

Every call is a PROPOSE — Tier W mints a card and applies nothing until redeemed, and this probe
never redeems one.
"""
import json, subprocess, sys, uuid
sys.path.insert(0, ".")
import httpx
from scripts.eval.tool_liveness import config as cfg
from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError
from scripts.toolloop.provision import Throwaway, _tle_auth

m = MCPDirect()


def sql(q):
    return subprocess.run(["docker", "exec", "-i", "infra-postgres-1", "psql", "-U", "loreweave",
                           "-d", "loreweave_glossary", "-tAF|", "-c", q],
                          capture_output=True, text=True).stdout.strip()


def build(label, stale):
    fx = Throwaway(label, mcp=m).build()
    httpx.post(f"{cfg.DOMAIN_BASE['glossary']}/v1/glossary/books/{fx.book_id}/adopt",
               headers=_tle_auth().bearer_header(),
               json={"genres": ["universal"], "kinds": ["character", "location"]}, timeout=60)
    if stale:
        sql(f"update book_kinds set source_hash='STALE-TEST-HASH' "
            f"where book_id='{fx.book_id}' and source_ref is not null")
    return fx


def call(**args):
    try:
        r = m.call("glossary_book_sync_apply", args)
        return {"verdict": "SUCCEEDED", "detail": json.dumps(r, ensure_ascii=False)[:200]}
    except MCPToolError as e:
        return {"verdict": "refused", "detail": str(e)[:260]}


a = b = None
out = {}
try:
    a = build("sync-ship-a", stale=True)     # has a divergence
    b = build("sync-ship-b", stale=False)    # up to date, and a DIFFERENT book
    avail = m.call("glossary_book_sync_available", {"book_id": a.book_id})
    rows = avail.get("updates") or []
    out["_fixture"] = {"book_a": a.book_id, "rows_available_a": len(rows),
                       "book_b": b.book_id,
                       "rows_available_b": len((m.call("glossary_book_sync_available",
                                                       {"book_id": b.book_id}).get("updates") or []))}
    a_row = rows[0]["id"] if rows else None

    out["empty_items"] = call(book_id=a.book_id, items=[])
    out["empty_items"]["asked"] = "items present but EMPTY — the falsifier says it must be refused, not defaulted"

    out["absent_row"] = call(book_id=a.book_id,
                             items=[{"entity": "kind", "id": str(uuid.uuid4()), "choice": "take_theirs"}])
    out["absent_row"]["asked"] = "an item naming a row id that does not exist"

    out["empty_case_book_up_to_date"] = call(
        book_id=b.book_id, items=[{"entity": "kind", "id": str(uuid.uuid4()), "choice": "take_theirs"}])
    out["empty_case_book_up_to_date"]["asked"] = "a book with NO available updates"

    if a_row:
        out["tenancy_row_from_other_book"] = call(
            book_id=b.book_id, items=[{"entity": "kind", "id": a_row, "choice": "take_theirs"}])
        out["tenancy_row_from_other_book"]["asked"] = "book A's sync row applied against book B"

        g = call(book_id=a.book_id, items=[{"entity": "kind", "id": a_row, "choice": "take_theirs"}])
        g["asked"] = "a VALID apply — must mint a card and change NOTHING yet"
        g["minted_token"] = ("confirm_token" in (g.get("detail") or "")
                             or "task" in (g.get("detail") or "").lower())
        out["gate"] = g
        out["gate"]["still_stale_after_propose"] = sql(
            f"select count(*) from book_kinds where book_id='{a.book_id}' "
            f"and source_hash='STALE-TEST-HASH'")
finally:
    for fx in (a, b):
        if fx:
            try:
                fx.teardown()
            except Exception as e:  # noqa: BLE001
                out.setdefault("_teardown_errors", []).append(str(e)[:120])
print(json.dumps(out, indent=2, ensure_ascii=False))
