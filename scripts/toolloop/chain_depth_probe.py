"""Does the path the model ACTUALLY takes fill the attributes it asks for?

composition_glossary_build exists because eval/schema_recall_poc.py measured that emitting every
kind's attributes in one blind pass produces empty/partial rows — "terminology produced EMPTY
rows, and power_system/item/organization got 2 of their 6-7 slots". Its answer is one focused
call per entity with a sliced schema.

The model never picks it. On 5 of 5 runs it takes glossary_extract_entities_from_doc instead,
which is ONE call returning candidates for every entity of every kind at once — the mixed-kind
shape by construction. This measures what that costs, on the tool the model really uses, against
a book whose ontology is adopted so the tool is grounded exactly as it is in a live turn.

Read-only: glossary_extract_entities_from_doc is Tier-R and writes nothing. One throwaway book,
torn down in `finally`.
"""
import json
import sys
from collections import defaultdict

sys.path.insert(0, ".")
import httpx  # noqa: E402

from scripts.eval.tool_liveness import config as cfg  # noqa: E402
from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError  # noqa: E402
from scripts.toolloop.provision import Throwaway, _tle_auth  # noqa: E402

m = MCPDirect()

# Deliberately spans the kinds the eval named as the failure cases, not just `character`.
KINDS = ["character", "location", "item", "organization", "terminology", "power_system"]

STORY = """\
Aldric Vane climbs the black stair of Hollow Keep as the storm breaks. Mira Solene waits at the
waterline where the Obsidian Trench is walkable only at low tide. Aldric carries the Ashen Sigil,
a cracked bronze medallion that grows cold near running water. The Wardens of the Pale are the
order that keeps the Keep, and they answer to no crown.

Their craft is called stillwater binding: a practitioner holds a volume of water perfectly
motionless and draws heat out of it, which is why every binder's hands are scarred with frost.
The term for a binder who has lost the knack is "drowned" — spoken plainly, not as an insult but
as a diagnosis, and a drowned binder is barred from the Trench at low tide.
"""


def fill_stats(attrs) -> tuple[int, int]:
    """(filled fields, total chars across filled fields). A field is filled when it carries
    something a reader could use — not merely present with an empty value."""
    if not isinstance(attrs, dict):
        return 0, 0
    filled = chars = 0
    for v in attrs.values():
        s = "" if v is None else (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
        s = s.strip()
        if s and s not in ("[]", "{}", '""', "null"):
            filled += 1
            chars += len(s)
    return filled, chars


fx = None
out: dict = {}
try:
    fx = Throwaway("chain-depth", mcp=m).build()
    out["_fixture"] = {"book_id": fx.book_id}

    r = httpx.post(
        f"{cfg.DOMAIN_BASE['glossary']}/v1/glossary/books/{fx.book_id}/adopt",
        headers=_tle_auth().bearer_header(),
        json={"genres": ["universal"], "kinds": KINDS}, timeout=90)
    out["adopt"] = {"status": r.status_code, "asked_kinds": KINDS}

    # DENOMINATOR from the system standards' own attribute_count — the schema size each kind
    # ASKS for. The book adopted exactly these kinds, so this is the shape the tool is grounded
    # in. (A book-ontology read was tried first and its response shape did not carry per-kind
    # attribute codes where I looked, which silently produced a 0 denominator and no fill_rate —
    # recorded rather than papered over.)
    std = m.call("glossary_list_system_standards", {})
    schema_size = {k.get("code"): int(k.get("attribute_count") or 0)
                   for k in (std.get("kinds") or []) if k.get("code")}
    out["schema_size"] = {k: schema_size.get(k) for k in KINDS}

    try:
        res = m.call("glossary_extract_entities_from_doc",
                     {"book_id": fx.book_id, "source_markdown": STORY})
        cands = res.get("candidates") or []
        out["extract"] = {"verdict": "SUCCEEDED", "candidates": len(cands)}
    except MCPToolError as e:
        cands = []
        out["extract"] = {"verdict": "refused", "detail": str(e)[:300]}

    per_kind = defaultdict(lambda: {"n": 0, "filled": 0, "asked": 0, "chars": 0, "names": []})
    for c in cands:
        kind = c.get("kind") or "(none)"
        f, ch = fill_stats(c.get("attributes"))
        asked = schema_size.get(kind, 0)
        row = per_kind[kind]
        row["n"] += 1
        row["filled"] += f
        row["asked"] += asked
        row["chars"] += ch
        row["names"].append(c.get("name"))

    out["per_kind"] = {}
    for kind, row in sorted(per_kind.items()):
        out["per_kind"][kind] = {
            "entities": row["n"],
            "names": row["names"][:6],
            "schema_fields_per_entity": (row["asked"] // row["n"]) if row["n"] else 0,
            "fields_filled_total": row["filled"],
            "fields_asked_total": row["asked"],
            "fill_rate": round(row["filled"] / row["asked"], 3) if row["asked"] else None,
            "chars_per_filled_field": round(row["chars"] / row["filled"], 1) if row["filled"] else 0,
        }
finally:
    if fx is not None:
        try:
            fx.teardown()
            out["torn_down"] = True
        except Exception as e:  # teardown failure must be visible, never swallowed
            out["torn_down"] = f"FAILED: {str(e)[:200]}"

print(json.dumps(out, indent=2, ensure_ascii=False))
