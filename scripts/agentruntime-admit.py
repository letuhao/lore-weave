#!/usr/bin/env python3
"""CP-4 · admit declarations into the manifest, **one at a time**, through the producer.

    python scripts/agentruntime-admit.py book_list [more ids...]
    python scripts/agentruntime-admit.py --list             # admissible vs admitted
    python scripts/agentruntime-admit.py --promote book_list  # CP-5.2 rung 2: draft -> admitted

🔴 **CP-5.2 — REGISTERING AND RELEASING ARE NOW DIFFERENT COMMANDS, AND BEFORE THIS THEY WERE THE
SAME ACCIDENT.** `derive_one` yields `draft` (derivation registers; it does not release), so every
run of this script rewrote `lifecycle` to `draft` — measured 2026-08-09 against a copy of the live
manifest: admitting a third declaration **silently demoted `book_list` and `book_read` off the
wire**, because `SERVED_LIFECYCLES` is `{admitted, deprecated}`. The two rows that served were
residue from before derivation stopped self-releasing, and nothing could have promoted them back:
`check_transition` documented the move and had **zero production callers**.

So this script now does two separable things:

* plain admission **carries each row's existing lifecycle forward** — re-deriving re-runs every
  contract clause without changing a release decision nobody made;
* `--promote` is the ONLY path to `admitted`, and it goes through `promotion.promote`, which
  refuses a tool whose `_meta.contract` is incomplete (rung 2).

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
from app.agentruntime.contract import Declaration  # noqa: E402
from app.agentruntime.derive import derive_one  # noqa: E402
from app.agentruntime.promotion import check_tool_contract, promote  # noqa: E402
from app.agentruntime.toolcontract import ToolContractViolation  # noqa: E402
from app.agentruntime.manifest import (  # noqa: E402
    load, manifest_path, readmission_queue,
)
from app.agentruntime import manifest as _manifest  # noqa: E402

BASELINE = ROOT / "contracts" / "agent-runtime-baseline" / "tools-list.snapshot.json"
#: CP-5.2 — the interim home for a tool contract, until the owning service publishes it in `_meta`.
CONTRACT_REGISTRY = ROOT / "contracts" / "agent-runtime-tool-contracts.json"


def catalogue() -> dict[str, dict]:
    """The frozen federated baseline **UNIONED WITH THE TOOLS CHAT-SERVICE SERVES ITSELF.**

    🔴 **§4 scopes rung 2 to *"all 324"* and this function used to see 315.** The four missing ones
    are not an edge case: they include `compose_prose` — the co-writer step the PO named as the
    point of the journey, and therefore an essential-set member that could not be admitted — and
    `glossary_propose_entity_edit`, the largest 0%-success tool in the whole corpus (101 calls / 12
    sessions), which for the same reason could carry no contract to fix it.

    **RAISES rather than degrading if the local tools cannot be read**, the rule
    `cp5-essential-set.py` already adopted for the same union: a partial catalogue here does not
    fail, it silently produces a manifest that is missing rows nobody asked about.
    """
    doc = json.loads(BASELINE.read_text(encoding="utf-8"))
    cat = {t["name"]: t for t in doc["tools"]}
    try:
        from app.services.local_tools import local_tool_defs
        local = local_tool_defs()
    except Exception as exc:  # noqa: BLE001 — a partial catalogue is worse than a loud failure
        raise SystemExit(
            f"cannot read chat-service's own tool definitions ({exc}). Admitting from a partial "
            f"catalogue is how the co-writer's tool came to look like a role nobody had ever used.")
    for d in local:
        fn = d.get("function", d)
        name = fn.get("name")
        if not name:
            raise SystemExit(f"a local tool definition carries no name: {d!r}")
        if name in cat:
            raise SystemExit(
                f"{name!r} is served BOTH locally and federated. That is a real ambiguity about "
                f"which definition a turn dispatches, not something this script may pick a side "
                f"on.")
        cat[name] = d
    return cat


def contract_registry() -> dict:
    """Absent is a legitimate empty state: it simply means nothing can be promoted yet."""
    if not CONTRACT_REGISTRY.exists():
        return {}
    return json.loads(CONTRACT_REGISTRY.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*", help="declaration ids to admit")
    ap.add_argument("--list", action="store_true", help="show admitted vs admissible")
    ap.add_argument("--promote", action="append", default=[], metavar="ID",
                    help="CP-5.2 rung 2: move a registered declaration draft -> admitted. Refused "
                         "unless the tool's _meta.contract covers every member that applies to it")
    args = ap.parse_args(argv)

    cat = catalogue()
    registry = contract_registry()
    path = manifest_path()
    current = load(path=path) if path and path.exists() else None
    rows = (current or {}).get("declarations", [])
    registered_ids = [r["id"] for r in rows]
    #: The release decision already on disk. Carried forward rather than re-derived, because
    #: derivation registers and does not release — re-deriving a served row into `draft` is the
    #: demotion this script used to perform silently.
    lifecycle_now = {r["id"]: r["lifecycle"] for r in rows}

    if args.list or not (args.ids or args.promote):
        served = [i for i, lc in lifecycle_now.items() if lc in ("admitted", "deprecated")]
        print(f"catalogue     {len(cat)} tools (frozen baseline)")
        print(f"manifest      {len(registered_ids)} registered: "
              f"{[(i, lifecycle_now[i]) for i in registered_ids]}")
        print(f"serving       {len(served)}: {served}")
        if current:
            print(f"queue         {readmission_queue(current)}")
        # Rung 2, as a report: what each registered row would need before it could be promoted.
        for i in registered_ids:
            if i in cat:
                rep = check_tool_contract(cat[i], registry=registry)
                state = "COMPLETE" if rep.is_complete else f"missing {list(rep.missing)}"
                print(f"  contract    {i:<24} {state}")
        return 0

    unknown = [i for i in (args.ids + args.promote) if i not in cat]
    if unknown:
        print(f"not in the catalogue: {unknown}")
        return 1

    # Re-admit everything already in the manifest ALONGSIDE the new ids: a declaration does not
    # leave the runtime, and `build` refuses to lose one. Re-deriving rather than copying the old
    # row is the point — it re-runs every clause against the current contract.
    want = sorted(set(registered_ids) | set(args.ids) | set(args.promote))
    missing = [i for i in want if i not in cat]
    if missing:
        print(f"already admitted but no longer in the catalogue: {missing}. That is a RETIREMENT, "
              f"which is a decision (see the third-party sunset row), not something this script "
              f"may take.")
        return 1

    derived = [derive_one(cat[i]) for i in want]
    declarations = []
    for d in derived:
        decl = d.declaration
        # Carry the release decision already recorded. A row that serves keeps serving; a row that
        # was never released stays `draft`. Neither is decided by re-running derivation.
        carried = lifecycle_now.get(decl.id, decl.lifecycle)
        if carried != decl.lifecycle:
            decl = Declaration(id=decl.id, kind=decl.kind, source_path=decl.source_path,
                               lifecycle=carried, members=decl.members)
        if decl.id in args.promote:
            try:
                decl = promote(decl, cat[decl.id], registry=registry)
            except ToolContractViolation as exc:
                rep = check_tool_contract(cat[decl.id], registry=registry)
                print(f"REFUSED  {decl.id}: rung 2 will not promote an incomplete contract.")
                print(f"  applies  {list(rep.applicable)}")
                print(f"  missing  {list(rep.missing)}")
                if rep.unknown:
                    print(f"  unknown  {list(rep.unknown)}")
                print(f"  {exc}")
                print("\nThe tool stays registered `draft` and does not reach the wire. Declare "
                      "the members in the owning service's `_meta.contract` and re-run "
                      "(CP-5 §4 rung 2).")
                return 1
            rep = check_tool_contract(cat[decl.id], registry=registry)
            print(f"PROMOTED {decl.id}: draft -> admitted, contract complete "
                  f"({len(rep.applicable)} members, declared in {rep.source})")
        declarations.append(decl)

    doc = _manifest.generate([admit(d) for d in declarations],
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
