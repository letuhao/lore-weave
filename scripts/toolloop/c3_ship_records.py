#!/usr/bin/env python3
"""Transcribe cycle 3's EXERCISED ship-audit results into its scenarios and evidence.

    python scripts/toolloop/c3_ship_records.py            # dry run
    python scripts/toolloop/c3_ship_records.py --apply

Same contract as `record_ship_exercised.py`, which did this for cycle 2: it ONLY transcribes, every
sentence names the file the claim rests on, and a case with no evidence is left exactly as it was.
`ship_audit` is a JUDGEMENT field fe_runner copies verbatim from the scenario (fe_runner.py:640) and
the gate checks "for PRESENCE rather than for truth", so writing it here is what a re-run would
produce for that field — no measured value is touched.

🔴 AND IT MUST NOT SNEAK PAST THE GATE. gate.py's SHIP bar rejects a value whose first 40 chars
contain one of `owed / not yet / todo / tbd / pending / n/a / later / skip`. My first draft wrote
registry_list_workflows' two cases as "INAPPLICABLE, NOT EXERCISED ..." and "NOT EXERCISED ..." —
neither phrase is in that list, so both would have PASSED the gate while saying in plain English
that nothing was exercised. They are prefixed "OWED —" so the gate refuses them, which is the
truthful outcome: that tool gets concluded `blocked` with a reason, not `proven`.

🔴 TWO THINGS IT REFUSES TO CALL A PASS, both learned the hard way in cycle 2:
  * a case the generic probe could not REACH. An op-dispatch tool declares only `op` as required, so
    ship_probe's absent/tenancy/empty cases all land on the op refusal and never touch the id. Those
    are transcribed from the TARGETED probe or not at all.
  * a zero-argument tool's "SUCCEEDED". With `required=[]` there is no id to make absent, none to
    make foreign and no field to empty; all three degenerate to the same call and succeeding is
    CORRECT. registry_list_workflows is that case and its cases are recorded as INAPPLICABLE, which
    is not the same as exercised.
"""
from __future__ import annotations

import argparse
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCEN = ROOT / "scripts" / "toolloop" / "scenarios-c3-run.json"
EVID = ROOT / "docs" / "eval" / "toolloop" / "2026-08-14"

E_SHIP = "docs/eval/toolloop/2026-08-14/c3-ship-probe.txt"
E_RUN = "docs/eval/toolloop/2026-08-14/c3-run.json"
E_BASE = "docs/eval/toolloop/2026-08-14/rebaseline.json"

OWED = ("owed", "not yet", "todo", "tbd", "pending", "n/a", "later", "skip")

RECORD: dict[str, dict[str, str]] = {
    "composition_arc_edit": {
        "absent_case": f"EXERCISED by TARGETED probe ({E_SHIP}). The generic sweep could not reach "
                       "it: only `op` is required, so all three cases landed on 'op=create requires "
                       "book_id' and never touched an id. Re-probed with op=delete + an absent "
                       "node_id — refused, 'not found or not accessible'. (op=archive was tried "
                       "first and is NOT in this tool's enum "
                       "[create|update|delete|restore|move|assign_chapters]; that refusal looks "
                       "like a boundary result and is not one.)",
        "tenancy": f"EXERCISED by targeted probe ({E_SHIP}): a foreign node_id refuses IDENTICALLY "
                   "to an absent one, so the refusal is no existence oracle.",
        "gate": f"EXERCISED live ({E_BASE}): Tier A, called 5/5, left SUSPENDED on an approval card "
                "5/5, and the owning store moved on 0/5 — the card was never approved and nothing "
                "was written without it.",
    },
    "glossary_deep_research": {
        "absent_case": f"EXERCISED by direct probe ({E_SHIP}): an absent entity_id is refused, "
                       "'book not accessible'.",
        "tenancy": f"EXERCISED by direct probe ({E_SHIP}): a foreign entity_id refuses IDENTICALLY.",
        "gate": f"EXERCISED live ({E_BASE}): this is a PAID tool and the gate is the whole audit — "
                "called 5/5 and left SUSPENDED on a confirm card 5/5, so it never spent without "
                "one. The store change on 5/5 is loreweave_knowledge.entity_access_log gaining one "
                "row per run: a read-side audit trail, not the research write, which is still "
                "behind the unapproved card.",
    },
    "world_map_add_marker": {
        "absent_case": f"EXERCISED by direct probe ({E_SHIP}): an absent map_id is refused with "
                       "'map not found — check the map_id (call world_map_list for valid ids)'.",
        "tenancy": f"EXERCISED by direct probe ({E_SHIP}): a foreign map_id refuses IDENTICALLY.",
    },
    "settings_provider_inventory": {
        "absent_case": f"EXERCISED by direct probe ({E_SHIP}): an absent provider_credential_id is "
                       "refused, 'not accessible'.",
        "tenancy": f"EXERCISED by direct probe ({E_SHIP}): a foreign provider_credential_id refuses "
                   "IDENTICALLY to an absent one.",
        "empty_case": f"EXERCISED by direct probe ({E_SHIP}): an empty value is refused by NAME — "
                      "'provider_credential_id must be a UUID'.",
    },
    "registry_list_workflows": {
        "absent_case": f"OWED — INAPPLICABLE AS PROBED ({E_SHIP}). required=[] — there is no id to "
                       "make absent, so the case does not exist for this tool. ship_probe printed "
                       "'🔴 SUCCEEDED — a boundary that does not hold' three times; that is a FALSE "
                       "ALARM it cannot detect, because an argument-less list read SUCCEEDING is "
                       "correct. Do not read this as a pass.",
        "tenancy": f"OWED — NOT EXERCISED ({E_SHIP}). Its real boundary is tenancy of the RESULT — whether "
                   "it returns another account's workflows — which needs a SECOND ACCOUNT and is "
                   "not what an absent/foreign id probe measures. Genuinely owed.",
    },
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    d = json.loads(SCEN.read_text(encoding="utf-8"))
    changed, still = 0, []
    for s in d["scenarios"]:
        rec = RECORD.get(s["tool_under_test"]) or {}
        audit = s.get("ship_audit") or {}
        for case, val in list(audit.items()):
            new = rec.get(case)
            if new and isinstance(val, str) and any(w in val.lower()[:40] for w in OWED):
                audit[case] = new
                changed += 1
                print(f"  {s['tool_under_test']:30} {case:12} <- {new[:70]}")
        for case, val in audit.items():
            if isinstance(val, str) and any(w in val.lower()[:40] for w in OWED):
                still.append(f"{s['tool_under_test']}.{case}")
    print(f"\n{changed} transcribed")
    if still:
        print(f"{len(still)} STILL OWED — no evidence exists, untouched:")
        for x in still:
            print(f"  {x}")
    if a.apply:
        SCEN.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        by = {s["tool_under_test"]: s.get("ship_audit") for s in d["scenarios"]}
        for name in ("c3-run.json",):
            p = EVID / name
            if not p.exists():
                continue
            ev = json.loads(p.read_text(encoding="utf-8"))
            n = 0
            for t in ev["tools"]:
                if by.get(t["tool"]) and t.get("ship_audit") != by[t["tool"]]:
                    t["ship_audit"] = by[t["tool"]]
                    n += 1
            p.write_text(json.dumps(ev, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"{name}: synced {n} tool(s)")
        print(f"wrote {SCEN}")
    else:
        print("\n(dry run — pass --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
