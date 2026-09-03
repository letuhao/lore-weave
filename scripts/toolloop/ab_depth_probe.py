"""A/B: the path the model TAKES vs the path it never takes, on one story.

composition_build_cast_and_graph exists because eval/schema_recall_poc.py measured that emitting every
kind's attributes in one blind pass produces empty/partial rows — "terminology produced EMPTY
rows, and power_system/item/organization got 2 of their 6-7 slots". Its answer is a breadth-only
plan, a depth tag per entity, then ONE focused call per entity with a sliced schema.

The model never picks it: on 5 of 5 runs it takes glossary_extract_entities_from_doc, which is a
single call covering every entity of every kind at once. This measures what that costs.

    ARM A  glossary_extract_entities_from_doc      (what the model always does)
    ARM B  composition_build_cast_and_graph start -> approve_plan -> status  (what it never does)

Same story, same adopted kinds, same fill metric, one throwaway book per arm, both torn down.
Arm A writes nothing (Tier-R). Arm B writes review DRAFTS into its own throwaway book and never
projects to the graph — no approve_edges, so nothing leaves the fixture.
"""
import json
import sys
import time
from collections import defaultdict

sys.path.insert(0, ".")
import httpx  # noqa: E402

from scripts.eval.tool_liveness import config as cfg  # noqa: E402
from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError  # noqa: E402
from scripts.toolloop.provision import Throwaway, _tle_auth  # noqa: E402

m = MCPDirect()
KINDS = ["character", "location", "item", "organization", "terminology", "power_system"]
MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"
STORY = (
    "Aldric Vane climbs the black stair of Hollow Keep as the storm breaks. Mira Solene waits at "
    "the waterline where the Obsidian Trench is walkable only at low tide. Aldric carries the "
    "Ashen Sigil, a cracked bronze medallion that grows cold near running water. The Wardens of "
    "the Pale are the order that keeps the Keep, and they answer to no crown.\n\n"
    "Their craft is called stillwater binding: a practitioner holds a volume of water perfectly "
    "motionless and draws heat out of it, which is why every binder's hands are scarred with "
    "frost. The term for a binder who has lost the knack is \"drowned\" — spoken plainly, not as "
    "an insult but as a diagnosis, and a drowned binder is barred from the Trench at low tide.")


def fill_stats(attrs):
    """(filled fields, chars across filled fields). Filled = carries something a reader can use,
    not merely present-and-empty."""
    if isinstance(attrs, list):
        # TWO list shapes, and guessing one cost a whole run: arm A returns {code, value}, while
        # glossary_get_entity returns {attribute_def:{code}, original_value, translations, ...}.
        # Reading the wrong keys yielded {None: None} and a flat 0.0 fill for every kind — a
        # perfect-looking finding that was entirely my mapper.
        norm = {}
        for a in attrs:
            if not isinstance(a, dict):
                continue
            code = (a.get("attribute_def") or {}).get("code") or a.get("code")
            val = a.get("original_value") if "original_value" in a else a.get("value")
            if code:
                norm[code] = val
        attrs = norm
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


def provision(label):
    fx = Throwaway(label, mcp=m).build()
    httpx.post(f"{cfg.DOMAIN_BASE['glossary']}/v1/glossary/books/{fx.book_id}/adopt",
               headers=_tle_auth().bearer_header(),
               json={"genres": ["universal"], "kinds": KINDS}, timeout=90)
    return fx


def tally(rows, schema_size):
    """rows: [(kind, name, attributes)] -> per-kind fill table."""
    per = defaultdict(lambda: {"n": 0, "filled": 0, "asked": 0, "chars": 0, "names": []})
    for kind, name, attrs in rows:
        f, ch = fill_stats(attrs)
        r = per[kind]
        r["n"] += 1
        r["filled"] += f
        r["asked"] += schema_size.get(kind, 0)
        r["chars"] += ch
        r["names"].append(name)
    out = {}
    for kind, r in sorted(per.items()):
        out[kind] = {
            "entities": r["n"], "names": r["names"][:6],
            "schema_fields_per_entity": schema_size.get(kind, 0),
            "filled": r["filled"], "asked": r["asked"],
            "fill_rate": round(r["filled"] / r["asked"], 3) if r["asked"] else None,
            "chars_per_filled_field": round(r["chars"] / r["filled"], 1) if r["filled"] else 0,
        }
    tf = sum(r["filled"] for r in per.values())
    ta = sum(r["asked"] for r in per.values())
    tc = sum(r["chars"] for r in per.values())
    out["_TOTAL"] = {"filled": tf, "asked": ta,
                     "fill_rate": round(tf / ta, 3) if ta else None,
                     "chars_per_filled_field": round(tc / tf, 1) if tf else 0}
    return out


out = {}
std = m.call("glossary_list_system_standards", {})
schema_size = {k.get("code"): int(k.get("attribute_count") or 0)
               for k in (std.get("kinds") or []) if k.get("code")}
out["schema_size"] = {k: schema_size.get(k) for k in KINDS}

# ── ARM A ────────────────────────────────────────────────────────────────────────
a = provision("ab-arm-a")
try:
    res = m.call("glossary_extract_entities_from_doc",
                 {"book_id": a.book_id, "source_markdown": STORY})
    rows = [(c.get("kind"), c.get("name"), c.get("attributes"))
            for c in (res.get("candidates") or [])]
    out["ARM_A_extract_entities_from_doc"] = tally(rows, schema_size)
    out["ARM_A_extract_entities_from_doc"]["_entities"] = len(rows)
except MCPToolError as e:
    out["ARM_A_extract_entities_from_doc"] = {"refused": str(e)[:300]}
finally:
    a.teardown()

# ── ARM B ────────────────────────────────────────────────────────────────────────
b = provision("ab-arm-b")
try:
    started = m.call("composition_build_cast_and_graph", {
        "op": "start", "book_id": b.book_id, "source_text": STORY,
        "model_ref": MODEL, "model_source": "user_model"})
    run_id, wl = started.get("run_id"), (started.get("worklist") or [])
    out["ARM_B_plan"] = {"n": len(wl),
                         "deep": [w.get("name") for w in wl if w.get("depth") == "deep"],
                         "standard": [w.get("name") for w in wl if w.get("depth") != "deep"]}
    m.call("composition_build_cast_and_graph",
           {"op": "approve_plan", "book_id": b.book_id, "run_id": run_id, "worklist": wl})
    status = None
    for _ in range(40):
        time.sleep(15)
        st = m.call("composition_build_cast_and_graph",
                    {"op": "status", "book_id": b.book_id, "run_id": run_id})
        status = st.get("status")
        if str(status).lower() not in ("running", "building", "in_progress", "pending"):
            out["ARM_B_status"] = {"status": status,
                                   "skipped": [i.get("name") for i in (st.get("items") or [])
                                               if i.get("skip_reason")]}
            break
    # `status` is VIEW-DEPENDENT: the schema advertises the union of every view's values, but
    # ai_suggestions accepts only draft|active|inactive|rejected|all — "proposed" is refused even
    # though op=status reports the items AS proposed. Two vocabularies, one field.
    lst = m.call("glossary_curation_list",
                 {"book_id": b.book_id, "view": "ai_suggestions", "status": "all"})
    items = lst.get("items") or lst.get("suggestions") or lst.get("entities") or []
    out["ARM_B_readback"] = {"listed": len(items), "list_keys": sorted(lst)[:8]}
    rows = []
    for it in items:
        eid = it.get("entity_id") or it.get("id")
        if not eid:
            continue
        try:
            ent = m.call("glossary_get_entity", {"book_id": b.book_id, "entity_id": eid})
            e = ent.get("entity") or ent
            # `kind` comes back as an OBJECT here ({code,name,...}) while arm A returns the bare
            # code — same field name, two shapes, so normalise before tallying.
            k = e.get("kind")
            kind = k.get("code") if isinstance(k, dict) else (k or e.get("kind_code"))
            if not out.get("_ARM_B_sample"):
                out["_ARM_B_sample"] = json.dumps(e, ensure_ascii=False)[:600]
            rows.append((kind, e.get("name"),
                         e.get("attributes") or e.get("attribute_values")))
        except MCPToolError:
            pass
    if rows:
        out["ARM_B_glossary_build"] = tally(rows, schema_size)
        out["ARM_B_glossary_build"]["_entities"] = len(rows)
    else:
        out["ARM_B_glossary_build"] = {"note": "no entities read back", "sample": items[:2]}
except MCPToolError as e:
    out["ARM_B_glossary_build"] = {"refused": str(e)[:300]}
finally:
    b.teardown()
    out["torn_down"] = True

print(json.dumps(out, indent=2, ensure_ascii=False))
