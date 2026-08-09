#!/usr/bin/env python3
"""CP-4 · admit declarations into the manifest, **one at a time**, through the producer.

    python scripts/agentruntime-admit.py book_list [more ids...]
    python scripts/agentruntime-admit.py --list        # what is admissible, and what is admitted

The catalogue read here is the FROZEN baseline (`contracts/agent-runtime-baseline/`), not a live
gateway. That is deliberate and it is the same reason the baseline exists at all: a declaration
admitted from a catalogue that no longer exists cannot be reproduced, and CP-4's whole claim is that
each admitted row is attributable. The live catalogue is measured separately; it agreed with the
baseline on all 315 ids when this was written.

**Every field comes from `derive.py`.** Nothing here authors a declaration — the board's rule is that
a mechanism produces them, and a script that could hand-write one row would be the exception that
makes the mechanism optional.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "chat-service"))

from app.agentruntime.admission import admit  # noqa: E402
from app.agentruntime.derive import derive_one  # noqa: E402
from app.agentruntime.manifest import (  # noqa: E402
    load, manifest_path, readmission_queue,
)
from app.agentruntime import manifest as _manifest  # noqa: E402

BASELINE = ROOT / "contracts" / "agent-runtime-baseline" / "tools-list.snapshot.json"


def catalogue() -> dict[str, dict]:
    doc = json.loads(BASELINE.read_text(encoding="utf-8"))
    return {t["name"]: t for t in doc["tools"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*", help="declaration ids to admit")
    ap.add_argument("--list", action="store_true", help="show admitted vs admissible")
    args = ap.parse_args(argv)

    cat = catalogue()
    path = manifest_path()
    current = load(path=path) if path and path.exists() else None
    admitted_ids = [r["id"] for r in (current or {}).get("declarations", [])]

    if args.list or not args.ids:
        print(f"catalogue     {len(cat)} tools (frozen baseline)")
        print(f"manifest      {len(admitted_ids)} admitted: {admitted_ids}")
        if current:
            print(f"queue         {readmission_queue(current)}")
        return 0

    unknown = [i for i in args.ids if i not in cat]
    if unknown:
        print(f"not in the catalogue: {unknown}")
        return 1

    # Re-admit everything already in the manifest ALONGSIDE the new ids: a declaration does not
    # leave the runtime, and `build` refuses to lose one. Re-deriving rather than copying the old
    # row is the point — it re-runs every clause against the current contract.
    want = sorted(set(admitted_ids) | set(args.ids))
    missing = [i for i in want if i not in cat]
    if missing:
        print(f"already admitted but no longer in the catalogue: {missing}. That is a RETIREMENT, "
              f"which is a decision (see the third-party sunset row), not something this script "
              f"may take.")
        return 1

    derived = [derive_one(cat[i]) for i in want]
    doc = _manifest.generate([admit(d.declaration) for d in derived],
                             path=path, bootstrap=current is None,
                             definitions={i: cat[i] for i in want})
    print(f"manifest      {len(doc['declarations'])} declaration(s) at contract "
          f"{doc['contract_version']}")
    for r in doc["declarations"]:
        print(f"  {r['id']:<28} {r['kind']:<9} {r['owning_service']:<26} "
              f"lane={r.get('lane', '-'):<7} cost={r.get('cost', '-')}")
    print(f"queue         {readmission_queue(doc)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
