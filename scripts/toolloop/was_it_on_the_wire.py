"""Did the model DECLINE the tool, or was it never offered one?

    python scripts/toolloop/was_it_on_the_wire.py [ROW ...]

A defect that says "the model did not call X" is a MODEL defect only if X was on the wire. If
it was not, the same evidence describes a SURFACING defect wearing a model defect's clothes,
and every remedy aimed at the model is aimed at the wrong half.

🔴 THIS IS NOT HYPOTHETICAL. D-THE-MODEL-ASKS-INSTEAD-OF-RAISING-THE-CARD-IT-HAS was filed as a
model defect on five runs where the model "asked instead of calling
composition_canon_rule_restore". The server's own record says that tool was advertised on 0 of
5 turns, along with every other canon-rule WRITE — the model was holding the read and nothing
else, and asking was the only action available to it. The row is now platform-class.

The answer comes from `chat_messages.advertised_tools`, which is the SERVER's per-pass record
of what it offered — not the harness's `surface` snapshot, which that row had already found is
taken before the turn's arming and cannot answer the question.

WHAT IT CANNOT TELL YOU. A turn that produced no assistant row has no `advertised_tools` at
all, so a timed-out run is UNKNOWN here, never "not advertised". The two are printed apart.
"""
from __future__ import annotations

import argparse
import glob
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"


def psql(sql: str) -> list[list[str]]:
    r = subprocess.run(["docker", "exec", "-i", "infra-postgres-1", "psql", "-U", "loreweave",
                        "-d", "loreweave_chat", "-At", "-F", "\x1f", "-c", sql],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stderr[:400])
    return [ln.split("\x1f") for ln in r.stdout.split("\n") if ln.strip()]


def sessions_for(batch: str) -> list[str]:
    out: list[str] = []
    for fp in glob.glob(str(ROOT / "docs" / "eval" / "toolloop" / "**" / f"{batch}*.json"),
                        recursive=True):
        try:
            runs = json.loads(pathlib.Path(fp).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(runs, list):
            out += [r["session_id"] for r in runs
                    if isinstance(r, dict) and r.get("session_id")]
    return sorted(set(out))


def wire_verdict(sessions: list[str], tool: str) -> dict:
    """Turns that ADVERTISED the tool, turns that did not, and turns with no record at all."""
    if not sessions:
        return {}
    ids = ",".join("'" + s + "'" for s in sessions)
    rows = psql(
        "SELECT m.session_id::text, "
        " (m.advertised_tools IS NOT NULL AND jsonb_typeof(m.advertised_tools)='array')::text, "
        " EXISTS (SELECT 1 FROM jsonb_array_elements(coalesce(m.advertised_tools,'[]'::jsonb)) p, "
        "   jsonb_array_elements_text(coalesce(p->'names','[]'::jsonb)) n "
        f"  WHERE n = '{tool}')::text "
        f"FROM chat_messages m WHERE m.role='assistant' AND m.session_id IN ({ids});")
    # 🔴 `::text` ON A BOOLEAN YIELDS `true`/`false`, NOT `t`/`f`. The first version compared
    # against "t", matched nothing, and reported every row as "no record" — a wrong answer that
    # looked exactly like a missing one, which is the failure this whole script exists to catch.
    # So the encoding is ASSERTED rather than assumed: an unexpected value stops the sweep
    # instead of quietly reading as False.
    def _b(v: str) -> bool:
        if v not in ("true", "false"):
            raise SystemExit(f"unexpected boolean encoding {v!r} from psql — refusing to guess")
        return v == "true"

    on = {r[0] for r in rows if len(r) >= 3 and _b(r[2])}
    recorded = {r[0] for r in rows if len(r) >= 3 and _b(r[1])}
    return {"sessions": len(sessions), "with_a_record": len(recorded),
            "advertised": len(on), "not_advertised": len(recorded - on),
            "no_record": len(set(sessions) - recorded)}


def tool_names_in(row: dict) -> list[str]:
    blob = json.dumps(row, ensure_ascii=False)
    known = {n for n in re.findall(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+){1,4}\b", blob)}
    # Only names the catalogue actually knows — the prose is full of snake_case that is not a tool.
    cache = json.loads((ROOT / "contracts" / "tool-catalog-cache.json").read_text(encoding="utf-8"))
    return sorted(n for n in known if n in cache)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rows", nargs="*", help="ledger row ids; default = every open model row")
    args = ap.parse_args()

    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    defects = led["defects"]
    ids = args.rows or [k for k, v in defects.items()
                        if v.get("state") == "open" and v.get("defect_class") == "model"]

    print(f"{len(ids)} row(s)\n")
    for rid in ids:
        row = defects.get(rid)
        if row is None:
            print(f"  ?? {rid}: not in the ledger")
            continue
        blob = json.dumps(row, ensure_ascii=False)
        batches = sorted({b for b in re.findall(r"\b(c-[a-z0-9]+|batch\d+)\b", blob)})
        sess: list[str] = []
        for b in batches:
            sess += sessions_for(b)
        sess = sorted(set(sess))
        tools = tool_names_in(row)
        print(f"── {rid}")
        print(f"   batches={batches[:4]} sessions={len(sess)} candidate tools={len(tools)}")
        if not sess:
            print("   NO SESSION IDS on disk — this row cannot be settled this way\n")
            continue
        for t in tools[:12]:
            v = wire_verdict(sess, t)
            if not v or v["with_a_record"] == 0:
                continue
            flag = "  <<< NEVER ON THE WIRE" if v["advertised"] == 0 else ""
            print(f"     {t:44s} advertised {v['advertised']}/{v['with_a_record']} recorded "
                  f"(+{v['no_record']} turns left no record){flag}")
        print()
    print("A tool at 0/N is not proof the row is misfiled — read the row and see whether that "
          "tool is the one it says the model declined. It IS proof the model was not offered it.")


if __name__ == "__main__":
    main()
