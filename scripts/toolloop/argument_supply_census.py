"""For each LOW-PUBLICATION argument: does a live tool RETURN that id, and was it on the wire?

OWNER DIRECTION, 2026-08-31, verbatim: "d->check the tool itself, it it follow standard? guard
cannot work because lack of parameters?" -- which re-aimed
D-FABRICATION-GUARD-IS-BLIND-TO-A-VALID-LOOKING-UUID at a hypothesis it had never stated: that a
fabricated id is a SUPPLY failure rather than a detection failure, and no guard can fix a value
the platform never gave the model. The row records the direction's next question as unanswered:

    "for each low-publication argument, does a LIVE tool exist that returns that id, and was it
     on the wire?"

This answers it. Six mechanisms have been measured and rejected on the DETECTION side; this is the
first measurement on the supply side.

DERIVED FROM WHAT RESULTS ACTUALLY RETURN, NOT FROM WHAT TOOLS DECLARE. A declared output field is
a promise; the question is what came back. Suppliers are found by scanning recorded tool RESULTS
recursively for the argument name (`jsonb_path_exists $.** ? (exists(@.<arg>))`) over calls that
returned ok.

🔴 tool_load IS EXCLUDED AND THAT EXCLUSION IS THE INSTRUMENT'S MAIN CORRECTION. It appears as a
"supplier" of EVERY argument, because it returns tool SCHEMAS and a schema DECLARES the argument
name. A tool that hands back `{"run_id": {"type": "string"}}` has supplied a declaration, not an
id. Counting it would have reported a supplier for every argument on the wire in every turn --
a census measuring itself. See also: a required-arg census cannot answer what comes back.

WHAT IT DOES NOT SHOW. Not whether the model UNDERSTOOD the supplier was the way to get the id --
an advertised, unused supplier is consistent with "would not" and with "did not realise", and this
cannot separate them. That limit is inherited from supplier_probe.py and stated again here.
"""
from __future__ import annotations

import collections
import json
import subprocess
import sys

#: The row's own per-argument publication rates, lowest first, plus one HIGH control. Without the
#: control a uniformly-empty result would read as a finding about low-publication arguments when
#: it was a finding about the query.
ARGS = [("source_entity_id", "5%"), ("target_entity_id", "11%"), ("run_id", "41%"),
        ("project_id", "54%"), ("world_id", "100% (control)")]

#: Returns tool SCHEMAS, so it names every argument without supplying one. See docstring.
NOT_A_SUPPLIER = {"tool_load", "tool_list"}


def psql(sql: str, db: str = "loreweave_chat") -> str:
    r = subprocess.run(
        ["docker", "exec", "-i", "infra-postgres-1", "psql", "-U", "loreweave", "-d", db,
         "-tA", "-F", "\t"],
        input=sql, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=900)
    if r.returncode != 0:
        raise SystemExit(f"psql failed: {r.stderr[:300]}")
    return r.stdout


def suppliers_for(arg: str) -> dict[str, int]:
    out = {}
    sql = f"""
SELECT c->>'tool', count(*)
FROM chat_messages m, jsonb_array_elements(m.tool_calls) c
WHERE m.tool_calls IS NOT NULL AND c->>'ok'='true'
  AND jsonb_typeof(c->'result')='object'
  AND jsonb_path_exists(c->'result', '$.** ? (exists(@.{arg}))')
GROUP BY 1 ORDER BY 2 DESC
"""
    for line in psql(sql).splitlines():
        p = line.split("\t")
        if len(p) == 2 and p[0] and p[0] not in NOT_A_SUPPLIER:
            out[p[0]] = int(p[1])
    return out


def on_the_wire(arg: str, suppliers: set[str]):
    """Of the calls that PASSED this argument, on how many was a supplier advertised?"""
    sql = f"""
SELECT m.advertised_tools::text
FROM chat_messages m, jsonb_array_elements(m.tool_calls) c
WHERE m.tool_calls IS NOT NULL AND m.advertised_tools IS NOT NULL
  AND jsonb_typeof(c->'args')='object'
  AND jsonb_path_exists(c->'args', '$.** ? (exists(@.{arg}))')
"""
    used, wired = 0, 0
    for line in psql(sql).splitlines():
        if not line.strip():
            continue
        try:
            adv = json.loads(line)
        except Exception:
            continue
        names = set()
        for p in adv if isinstance(adv, list) else []:
            if isinstance(p, dict):
                names.update(p.get("names") or [])
        used += 1
        if names & suppliers:
            wired += 1
    return used, wired


def main() -> int:
    print("SUPPLY-SIDE CENSUS for D-FABRICATION-GUARD-IS-BLIND-TO-A-VALID-LOOKING-UUID")
    print("(suppliers derived from what results RETURN; tool_load/tool_list excluded -- they "
          "return schemas, which NAME every argument without supplying one)\n")
    rows = []
    for arg, rate in ARGS:
        sup = suppliers_for(arg)
        used, wired = on_the_wire(arg, set(sup))
        rows.append((arg, rate, sup, used, wired))
        top = ", ".join(f"{k}({v})" for k, v in list(sup.items())[:3]) or "NONE"
        pct = f"{100 * wired / used:.0f}%" if used else "n/a"
        print(f"  {arg:20} pub {rate:15} suppliers={len(sup):2}  {top}")
        print(f"  {'':20} calls passing it: {used:5}   a supplier was advertised on "
              f"{wired} ({pct})\n")

    print("=" * 92)
    none = [a for a, _, s, _, _ in rows if not s]
    if none:
        print(f"ARGUMENTS WITH NO LIVE SUPPLIER AT ALL: {', '.join(none)}")
        print("  -> for these the direction's hypothesis holds outright: the platform never hands "
             "the model this id, so no detection rule can be the fix.")
    else:
        print("EVERY argument measured has at least one real supplier, so 'no supplier exists' is "
              "NOT the general explanation. What varies is whether it was ON THE WIRE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
