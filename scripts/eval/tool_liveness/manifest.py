"""Emit `contracts/tool-liveness.json` — the CD4 ship gate's source of truth.

CD4: *"The passing set is **generated** (`matrix.json`), never hand-maintained."*

Consumers (agent-registry Go, chat-service Python) must not re-derive the verdict logic in
two languages — that is the schema-drift trap this repo keeps stepping in. So the manifest
carries two DERIVED booleans and the consumers only read them:

    executes        : true  — the tool ran successfully when called correctly (G3 PASS, or
                              the capability re-probe passed after a G1 miss). For a
                              WORKFLOW-CRITICAL tool this also means its effect landed (a
                              silent success — ok but no effect — folds to false here).
                      false — the tool FAILED when called correctly. Proven broken.
                      null  — never checked (paid, no authored args, or no probe at all).
    proven          : true  — every gate G1..G4 passed under a real model.
    effect_verified : true  — WS-D4: the tool's effect was confirmed via an INDEPENDENT
                              read-back (the domain DB directly, per CD3), not just a 200-OK.
                              Present only when earned (matrix PASS, or the critical-set
                              effect pass); absent otherwise. Informational — the gate keys
                              on `executes`, into which a failed critical effect already
                              folds. `proven ⊆ effect_verified`.

The three-valued `executes` is load-bearing. `null` must NEVER be treated as `false`:
"we didn't check" is not "it's broken", and a gate that blocks on unknown would refuse
every unprobed tool in the catalog. Symmetrically it must never be treated as `true`.

Usage:
    python -m scripts.eval.tool_liveness.manifest docs/eval/tool-liveness/<date>/matrix.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .waivers import waiver_for

MANIFEST_PATH = Path("contracts/tool-liveness.json")

# The SoT above is not reachable from inside a service container, and neither Go's
# `go:embed` nor Python's package data can climb out of their module. So the generator
# owns per-service copies and a drift test in each service pins them byte-for-byte
# against the SoT. Nobody hand-edits any of them.
CONSUMER_COPIES = (
    Path("services/agent-registry-service/internal/api/tool-liveness.json"),
    Path("services/chat-service/app/services/tool-liveness.json"),
)
SCHEMA_VERSION = 2  # v2 (D-TRACKD-REACCOUNT): rows may carry `waived:{reason,gate}`


def _executes(row: dict) -> bool | None:
    """Can this tool execute when called correctly?

    G3 is the execution gate under the model. When G1 missed, the model never called it,
    so G3 is null and the deterministic capability re-probe is the only evidence.
    """
    if row.get("G3") == "PASS":
        return True
    if row.get("G3") == "RED":
        return False
    cap = row.get("capability")
    if cap == "PASS":
        return True
    if cap == "RED":
        return False
    return None  # SKIP-PAID / SKIP-NO-ARGS / not probed


def build(rows: list[dict], meta: dict[str, Any], sweep: list[dict] | None = None) -> dict:
    """Merge the two evidence sources.

    The NL matrix answers `proven` (every gate passed under a real model). The
    deterministic capability sweep answers `executes` for far more tools, cheaply. They
    are different questions and neither subsumes the other:

      * a sweep-only tool has `executes: true` but `proven: false` — it works when called,
        but no model has been shown to select it and produce a verified effect. It WARNS
        in validateWorkflow, and is still advertised.
      * the matrix wins wherever both have an opinion: it drove the tool through a real
        model, which is strictly more evidence.
    """
    tools: dict[str, dict] = {}
    for r in sweep or []:
        # A tool can appear in the sweep more than once — it runs in >1 phase (a motif read
        # is `null` in phase 1 against the real account, then PASS in phase 2 as the seeded
        # throwaway user). A CONCLUSIVE result must never be clobbered by a later `null`:
        # "we didn't check this phase" must not erase "it executed last phase". This makes
        # the merge independent of phase order, instead of relying on phase 2 running last.
        prior = tools.get(r["tool"])
        if prior is not None and r["executes"] is None and prior.get("executes") is not None:
            continue
        entry = {
            "status": "SWEEP-" + ("PASS" if r["executes"] else
                                  "BROKEN" if r["executes"] is False else "INCONCLUSIVE"),
            "executes": r["executes"],
            "proven": False,  # a deterministic call is not a model selecting it
        }
        # WS-D4: the workflow-critical set carries a stronger claim — its effect was verified
        # via an independent read-back, not just a 200-OK. Carry the flag only when earned
        # (kept lean; a null-effect row omits it), and never let a later null erase a True.
        ev = r.get("effect_verified")
        ev = ev if ev is not None else (prior or {}).get("effect_verified")
        if ev is not None:
            entry["effect_verified"] = ev
        tools[r["tool"]] = entry
    for r in rows:
        status = r.get("status", "?")
        prior = tools.get(r["tool"], {})
        ex = _executes(r)
        entry = {
            "status": status,
            # the matrix wins when it has an opinion; otherwise keep the sweep's
            "executes": ex if ex is not None else prior.get("executes"),
            "proven": status == "PASS",
        }
        # a matrix PASS is G1–G4 (effect included); otherwise keep any effect the sweep proved
        ev = True if status == "PASS" else prior.get("effect_verified")
        if ev is not None:
            entry["effect_verified"] = ev
        tools[r["tool"]] = entry
    # WS-D4 (D-TRACKD-REACCOUNT): a tool that is not `executes:true` must carry an EXPLICIT
    # `waived:{reason,gate}` IN THE MANIFEST — the exit-criterion mechanism that was missing.
    # We stamp AFTER the merge so a tool the sweep proved `true` is never waived (executes:true
    # wins). A `waived` NEVER covers `executes:false` — that stays a BROKEN tool the ship gate
    # rejects; `waiver_for` only annotates null/false-free non-true rows, and build asserts a
    # false row is not silently waived below.
    for name, entry in tools.items():
        if entry.get("executes") is True:
            continue
        w = waiver_for(name)
        if entry.get("executes") is False and w is not None:
            raise ValueError(
                f"{name!r} is executes:false (BROKEN) but has a waiver — a waive must never hide "
                "a broken tool; remove the waiver or fix the tool."
            )
        if w is not None:
            entry["waived"] = w
    # FAIL CLOSED at GENERATION (M5 review Q5): the invariant "every executes:null tool carries a
    # waiver" must hold at build time, not only when someone re-runs the test suite — otherwise a
    # NEW null tool from a future sweep silently ships as a bare null and the prose-only-waive class
    # the audit killed re-enters undetected. Mirror the false+waiver fail-closed above.
    orphans = sorted(n for n, e in tools.items() if e.get("executes") is None and "waived" not in e)
    if orphans:
        raise ValueError(
            f"executes:null tools with NO waiver (prose-only-waive class): {orphans}. "
            "Add each to scripts/eval/tool_liveness/waivers.py with a reason + gate, or fix the sweep."
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "source": meta.get("source", "?"),
        "generated_from_matrix_date": meta.get("date", "?"),
        "agent_model_ref": meta.get("model_ref", "?"),
        "note": (
            "GENERATED by scripts/eval/tool_liveness/manifest.py — do not hand-edit (CD4). "
            "`executes: null` means NOT CHECKED and must never be read as false. A tool "
            "absent from `tools` is unproven, not broken."
        ),
        "tools": dict(sorted(tools.items())),
    }


def blocked(manifest: dict, tool: str) -> bool:
    """The one predicate the ship gate blocks on. Explicit false only."""
    return manifest.get("tools", {}).get(tool, {}).get("executes") is False


def unproven(manifest: dict, tool: str) -> bool:
    return not manifest.get("tools", {}).get(tool, {}).get("proven", False)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = Path(sys.argv[1])
    data = json.loads(src.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("rows", [])
    meta = {} if isinstance(data, list) else data.get("meta", {})
    meta.setdefault("source", str(src).replace("\\", "/"))
    sweep = None
    if len(sys.argv) > 2:
        sweep_path = Path(sys.argv[2])
        sweep = json.loads(sweep_path.read_text(encoding="utf-8"))
        meta["source"] = meta["source"] + " + " + str(sweep_path).replace("\\", "/")
    out = build(rows, meta, sweep)
    body = json.dumps(out, indent=2, ensure_ascii=False) + "\n"
    for path in (MANIFEST_PATH, *CONSUMER_COPIES):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    n_block = sum(1 for t in out["tools"].values() if t["executes"] is False)
    n_proven = sum(1 for t in out["tools"].values() if t["proven"])
    n_unknown = sum(1 for t in out["tools"].values() if t["executes"] is None)
    print(f"wrote {MANIFEST_PATH} (+{len(CONSUMER_COPIES)} service copies): "
          f"{len(out['tools'])} tools · {n_proven} proven · "
          f"{n_block} BLOCKED (executes=false) · {n_unknown} unchecked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
