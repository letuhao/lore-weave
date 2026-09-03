#!/usr/bin/env python3
"""The v1-retirement RUN-STATE — DERIVED from the code, never typed.

🔴 WHY THIS EXISTS. The 2026-09-03 audit found the predecessor's slice board sitting at `pending`
for three slices that had shipped six weeks earlier, five more documents carrying counts that
disagreed with their own generators, and a ledger headline reading `200 of 198` because its
numerator was derived and its denominator was a frozen constant.

Every one of those was a number a human typed into a document. So this plan's board is a program.
If a clause here cannot be derived from the repository, it prints UNKNOWN and says what would
settle it — it never guesses, and it never prints a number it did not compute.

Usage:
    python scripts/v1_retire/runstate.py            # the board
    python scripts/v1_retire/runstate.py --json     # machine-readable
    python scripts/v1_retire/runstate.py --check    # exit 1 while v1 is not dead (for CI)
"""
from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

FE_TOOLS = ROOT / "services/chat-service/app/services/frontend_tools.py"
TOOL_DISCOVERY = ROOT / "services/chat-service/app/services/tool_discovery.py"
CATALOG = ROOT / "contracts/tool-catalog-cache.json"
MANIFEST = ROOT / "contracts/agent-runtime-manifest.json"
FE_CONTRACT = ROOT / "contracts/browser-tools.contract.json"

V1_TOOLS = ("confirm_action", "glossary_confirm_action", "glossary_propose_entity_edit")

#: Tools that are legitimately consumer-local and are NOT v1. Derived from the audit, and named
#: here so D2 can distinguish "chat-service serves a schema it should not" from "a discovery
#: meta-tool that has no domain to belong to". Widen this deliberately, never by accident.
CONSUMER_LOCAL_OK = {"tool_list", "tool_load", "compose_prose", "workflow_list", "workflow_load"}

UNKNOWN = "UNKNOWN"


def _read(p: pathlib.Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return None


def _string_set_assignment(src: str, name: str) -> set[str] | None:
    """Every string literal in the assignment to `name`, via AST.

    🔴 AST, NOT A REGEX. A substring scan over this file matches the same names inside the long
    NOTE comments that record the P2.2/P3.2 moves — the file mentions `propose_edit` and the seven
    `ui_*` names repeatedly in prose while deliberately NOT containing them in the set. A regex
    would report the set as non-empty forever.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == name for t in targets):
            continue
        if node.value is None:
            return set()
        return {n.value for n in ast.walk(node.value)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    return None


def _defines(src: str, *names: str) -> dict[str, bool]:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {n: False for n in names}
    defined = {n.name for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return {n: (n in defined) for n in names}


def _catalog() -> tuple[dict, str | None]:
    raw = _read(CATALOG)
    if raw is None:
        return {}, "catalogue cache missing"
    try:
        return json.loads(raw), None
    except ValueError as exc:
        return {}, f"catalogue cache unreadable: {exc}"


def _visibility(row: dict) -> str:
    """Live rows carry NO `visibility` key; only legacy ones are labelled.

    🔴 The audit's own first pass used one sentinel for 'absent from catalogue' and 'no visibility
    key', which made 199 live tools look absent. Two distinct answers, two distinct returns.
    """
    return (row.get("meta") or {}).get("visibility", "live")


def _enclosing_symbol(src: str, path: pathlib.Path, line0: int) -> str:
    """The function a 0-indexed line sits in — the STABLE key for an exemption.

    🔴 THE EXEMPTION REGISTRY WAS KEYED ON `file:line` AND IT BROKE THE FIRST TIME I EDITED THE
    FILE. Inserting one resolver into composition-service/app/mcp/server.py shifted every line
    below it by ~50, so six cited exemptions stopped matching their sites and the census jumped
    from 6 remaining to 11 while reporting `exempt: 2`. A registry keyed on a coordinate that any
    unrelated edit moves is a registry that silently empties itself — the same failure as deriving
    `last_batch` from a filename convention.

    A symbol survives edits above it. It does not survive a rename, which is the point: a rename
    should force the exemption to be re-justified rather than quietly following the code.
    """
    if path.suffix == ".py":
        try:
            tree = ast.parse(src)
        except SyntaxError:
            return "?"
        best, best_line = "?", -1
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if n.lineno - 1 <= line0 and n.lineno - 1 > best_line:
                    best, best_line = n.name, n.lineno - 1
        return best
    # Go: nearest preceding `func ...(` declaration.
    lines = src.splitlines()
    for i in range(min(line0, len(lines) - 1), -1, -1):
        m = re.match(r"func\s+(?:\([^)]*\)\s*)?(\w+)\s*\(", lines[i])
        if m:
            return m.group(1)
    return "?"


def _gate_census() -> dict:
    """Confirm-minting sites that never open a durable task.

    Pairs each `mint_confirm_token` / `MintConfirmToken` against a `gate_or_confirm` /
    `GateOrConfirm` within +/-30 lines. A mint that IS paired is the `confirm_fallback` closure
    being passed INTO the gate — gated, not ungated. Counting raw mints reports 15 in
    composition-service where the true ungated figure is 7.
    """
    # 🔴 EVERY MINT NAME, NOT JUST THE KIT'S. This read `mint_confirm_token|MintConfirmToken`
    # only, and knowledge-service mints with its OWN helper — `mint_action_token`
    # (app/ontology/confirm.py:160, "Python port of glossary's action_confirm_token.go"), used by
    # build_tools.py and graph_schema_tools.py. That service has no task gate at all, so an entire
    # service's ungated confirm-minting was invisible and D4 could have reported PASS over it.
    # A census keyed on one spelling measures the services that happened to use that spelling.
    mint = re.compile(r"\b(?:mint_confirm_token|MintConfirmToken|mint_action_token)\s*\(")
    gate = re.compile(r"\b(?:gate_or_confirm|GateOrConfirm)\s*\(")
    skip = re.compile(r"^\s*(#|//)|\bdef |\bfunc |import ")
    out: dict[str, list[str]] = {}
    for path in sorted(ROOT.glob("services/*/")):
        svc = path.name
        for f in list(path.rglob("*.py")) + list(path.rglob("*.go")):
            # 🔴 as_posix(), NOT str(). On Windows `str(Path)` yields backslashes, so a
            # `"/tests/" in s` filter never matches and every test fixture is counted as a
            # production call site — measured here as 28 ungated sites against a true 14,
            # with test files for `mint_confirm_token` making up the difference.
            s = f.as_posix()
            if "_test" in s or "/tests/" in s or "/test/" in s or "/build/" in s:
                continue
            src = _read(f)
            if src is None:
                continue
            lines = src.splitlines()
            mints = [i for i, l in enumerate(lines) if mint.search(l) and not skip.search(l)]
            if not mints:
                continue
            gates = [i for i, l in enumerate(lines) if gate.search(l) and not skip.search(l)]
            for m in mints:
                if not any(-30 <= g - m <= 30 for g in gates):
                    rel = f.relative_to(ROOT).as_posix()
                    sym = _enclosing_symbol(src, f, m)
                    # `file::symbol` is the key; the line rides along for a human to jump to and
                    # is deliberately NOT part of the identity.
                    out.setdefault(svc, []).append(f"{rel}::{sym}  (line {m + 1})")
    return out


def _exempt_sites() -> set[str]:
    """`file:line` for every site with a cited GATE-2 exemption.

    Only the `exemptions` array counts. The `_unclassified_*` block beside it is prose listing
    sites nobody has decided about yet, and is deliberately NOT read — a site becomes exempt by
    someone quoting the code that makes a GATE-2 class true, never by appearing in a list.
    """
    p = ROOT / "scripts" / "v1_retire" / "gate_exemptions.json"
    try:
        rows = json.loads(p.read_text(encoding="utf-8")).get("exemptions") or []
    except (OSError, ValueError):
        return set()
    out = set()
    for r in rows:
        if not (r.get("class") and r.get("reason") and r.get("cited_at") and r.get("symbol")):
            # An exemption without its citation is a claim, not evidence. Ignore it so the site
            # stays counted rather than silently disappearing from the denominator.
            continue
        out.add(f"{r['file']}::{r['symbol']}")
    return out


def collect() -> dict:
    d: dict = {}
    fe_src = _read(FE_TOOLS)
    cat, cat_err = _catalog()

    # ---- D1: the construct is gone -------------------------------------------------
    if fe_src is None:
        d["d1"] = {"state": "PASS", "detail": "frontend_tools.py does not exist"}
    else:
        names = _string_set_assignment(fe_src, "FRONTEND_TOOL_NAMES")
        fns = _defines(fe_src, "is_frontend_tool", "validate_frontend_tool_args",
                       "generic_frontend_tool_def")
        live = sorted(names & set(V1_TOOLS)) if names is not None else None
        d["d1"] = {
            "state": "FAIL" if (live or fns["is_frontend_tool"]) else "PASS",
            "frontend_tool_names": live if live is not None else UNKNOWN,
            "functions_still_defined": sorted(k for k, v in fns.items() if v),
            "detail": ("FRONTEND_TOOL_NAMES could not be parsed — settle by reading the assignment"
                       if names is None else ""),
        }
        imp = subprocess.run(
            ["git", "grep", "-l", "-E", r"from app\.services\.frontend_tools|import frontend_tools",
             "--", "services/"],
            cwd=ROOT, capture_output=True, text=True)
        files = [x for x in imp.stdout.splitlines() if x and "/tests/" not in x]
        d["d1"]["production_importers"] = files

    # ---- D2: nothing chat-service-local reaches the model ---------------------------
    td = _read(TOOL_DISCOVERY)
    core = _string_set_assignment(td, "ALWAYS_ON_CORE_NAMES") if td else None
    in_catalog = {t: (t in cat) for t in V1_TOOLS}
    offenders = sorted(t for t in V1_TOOLS if not in_catalog[t])
    d["d2"] = {
        "state": "FAIL" if offenders else ("UNKNOWN" if cat_err else "PASS"),
        "v1_in_federated_catalogue": in_catalog,
        "advertised_from_always_on_core": (
            sorted(set(V1_TOOLS) & core) if core is not None else UNKNOWN),
        "consumer_local_allowlist": sorted(CONSUMER_LOCAL_OK),
        "detail": cat_err or (
            "a v1 tool absent from the catalogue is served by the generic_frontend_tool_def "
            "fallback — that IS the v1 condition" if offenders else ""),
    }

    # ---- D3: the manifest declaration's owner --------------------------------------
    raw = _read(MANIFEST)
    try:
        decls = json.loads(raw)["declarations"] if raw else []
    except (ValueError, KeyError):
        decls = []
    rows = [x for x in decls if x.get("id") in V1_TOOLS]
    bad = [x for x in rows
           if x.get("owning_service") == "chat-service" and x.get("lifecycle") in
           ("admitted", "deprecated")]
    d["d3"] = {
        "state": "FAIL" if bad else ("PASS" if decls else UNKNOWN),
        "rows": [{"id": x["id"], "owning_service": x.get("owning_service"),
                  "lifecycle": x.get("lifecycle")} for x in rows],
        "detail": "" if decls else "manifest unreadable",
    }

    # ---- D4: the gate is total where a task is possible -----------------------------
    #
    # 🔴 D4 IS "OPENS A TASK **OR** CITES A GATE-2 EXEMPTION", so the exemptions must be
    # subtracted here. Counting every ungated site as a defect makes D4 unreachable — the same
    # shape as the anti-vacuity guards that now fail because the loop finished: an instrument
    # whose success condition cannot occur is not measuring, it is just red.
    #
    # Five composition sites are exempt on the code's OWN reasoning (server.py:347-355, the
    # ledger-guarded KIND-C confirms whose `_execute_*` needs the confirm token as a replay-ledger
    # / billing key) — GATE-2 class (a), verbatim.
    census = _gate_census()
    exempt = _exempt_sites()
    remaining = {svc: [s for s in sites if s.split("  (line")[0] not in exempt]
                 for svc, sites in census.items()}
    remaining = {k: v for k, v in remaining.items() if v}
    n_exempt = sum(1 for sites in census.values() for s in sites if s.split("  (line")[0] in exempt)
    d["d4"] = {
        "state": "FAIL" if remaining else "PASS",
        "ungated_mint_sites": {k: len(v) for k, v in sorted(remaining.items())},
        "total": sum(len(v) for v in remaining.values()),
        "exempt": n_exempt,
        "sites": {k: v for k, v in sorted(remaining.items())},
        "detail": ("each remaining site must open a durable task OR gain a row in "
                   "scripts/v1_retire/gate_exemptions.json citing one of GATE-2's four classes "
                   "(mcp-tool-io.md GATE-2)"),
    }

    # ---- Supporting: the contract's v1 slice ----------------------------------------
    try:
        fc = json.loads(_read(FE_CONTRACT) or "{}")
    except ValueError:
        fc = {}
    d["contract"] = {
        "total_entries": len(fc) or UNKNOWN,
        "v1_entries": sorted(set(fc) & set(V1_TOOLS)),
        "migrated_entries": sorted(set(fc) - set(V1_TOOLS)),
    }

    # ---- Supporting: catalogue census + freshness -----------------------------------
    if cat:
        legacy = [n for n, r in cat.items() if _visibility(r) == "legacy"]
        d["catalogue"] = {"total": len(cat), "live": len(cat) - len(legacy), "legacy": len(legacy)}
    else:
        d["catalogue"] = {"total": UNKNOWN, "detail": cat_err}

    # ---- D8: every service this loop touched still IMPORTS -------------------------
    #
    # 🔴 THE BOARD WENT GREEN OVER A SERVICE THAT COULD NOT START. D4's census is a SOURCE scan —
    # it counts mint sites and gate calls by reading text — so it cannot see a NameError. On
    # 2026-09-03 it reported `v1 IS DEAD` with `--check` exiting 0 while translation-service
    # raised `NameError: DESC_JOB_RESUME` on import, because the gate call referenced two
    # descriptors the module never imported.
    #
    # A clause that reads code cannot certify that the code RUNS. This one imports each touched
    # service's MCP module in a subprocess and fails on a non-zero exit.
    # 🔴 COLLECTION, NOT A BARE `import`. The first version ran
    # `python -c "import app.mcp.server"` in the service directory and reported four services
    # broken — every one a FALSE POSITIVE from the host, not the code: it resolved
    # `loreweave_mcp` from a stale copy in site-packages instead of `sdks/python`, and
    # chat-service's settings need env vars that no bare import supplies.
    #
    # A check that cannot tell host drift from a code defect is worse than no check: it would
    # have read RED for the whole loop and been ignored within a day. `pytest --collect-only`
    # imports every test module — and through them the service modules — using the SAME
    # conftest and path setup the suites use, so a NameError like the one that started this
    # (`DESC_JOB_RESUME` referenced at module level, never imported) still fails loudly while a
    # stale site-packages copy does not.
    import_failures = {}
    for svc in ("translation-service", "composition-service", "chat-service",
                "knowledge-service"):
        root = ROOT / "services" / svc
        if not (root / "tests").is_dir():
            continue
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q", "--no-header"],
            cwd=root, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            errs = [l for l in (r.stdout or "").splitlines() if l.startswith("ERROR ")]
            import_failures[svc] = errs[0] if errs else f"collection exit {r.returncode}"
    d["d8"] = {
        "state": "FAIL" if import_failures else "PASS",
        "failures": import_failures,
        "detail": "a source-only board cannot tell a gated service from an unimportable one",
    }

    # ---- D5: deprecated means dead, to the model UNAIDED ---------------------------
    #
    # BEHAVIOURAL. The check CALLS tool_load_result with a legacy name absent from the turn
    # catalogue — the state drop_superseded_tools leaves every turn — and requires a refusal that
    # NAMES the successor. Grepping this file for the string "deprecated" would pass on a comment,
    # and this repo has shipped three guards that did exactly that.
    probe = ROOT / "scripts" / "v1_retire" / "d5_probe.py"
    r = subprocess.run([sys.executable, str(probe)], cwd=ROOT / "services" / "chat-service",
                       capture_output=True, text=True, timeout=300)
    out = (r.stdout or "").strip().splitlines()
    verdict = out[-1] if out else f"FAIL:probe did not run (exit {r.returncode})"
    d["d5"] = {
        "state": "PASS" if verdict == "OK" else "FAIL",
        "detail": ("tool_load REFUSES a legacy name and names its successor; pinned_legacy is KEPT "
                   "(DQ-V3) — a user's explicit pin is not the model reaching a dead tool"),
        "probe": verdict,
    }

    # ---- D6: no document describes v1 as CURRENT -----------------------------------
    #
    # A doc may NAME the deleted module — a decision record that cites it is evidence, and
    # rewriting it destroys what it is evidence of. What it may not do is leave a reader thinking
    # the path is live. So naming it is fine; naming it WITHOUT saying it is gone is not.
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import gates  # noqa: PLC0415
    _GONE = ("V1-PATH-REDIRECT", "deleted 2026-09-03", "no longer exists", "is deleted")
    undeclared = []
    for doc in gates._docs():
        txt = doc.read_text(encoding="utf-8", errors="replace")
        if "frontend_tools.py" in txt and not any(g in txt for g in _GONE):
            undeclared.append(doc.as_posix().replace(ROOT.as_posix() + "/", ""))
    g4 = gates.g4_doc_count_drift()
    d["d6"] = {
        "state": "PASS" if not undeclared and g4[0] == "GREEN" else "FAIL",
        "docs_naming_a_deleted_module_as_live": undeclared,
        "count_drift": g4[1],
        "detail": "a doc may CITE frontend_tools.py as history; it may not leave it looking live",
    }

    # ---- D7: regression is impossible, not merely unlikely -------------------------
    #
    # Both halves matter. Green gates over a VACUOUS gate is the failure this whole loop is about:
    # G3 was green on the live repo while reading a key `_gate_census()` never returns, and its
    # selftest agreed, because the selftest fed it a shape the production caller never produces.
    st = subprocess.run([sys.executable, str(ROOT / "scripts/v1_retire/gates.py"), "--selftest"],
                        capture_output=True, text=True, timeout=900)
    gr = subprocess.run([sys.executable, str(ROOT / "scripts/v1_retire/gates.py")],
                        capture_output=True, text=True, timeout=900)
    red = [l for l in (gr.stdout or "").splitlines() if l.startswith("OVERALL")]
    d["d7"] = {
        "state": "PASS" if st.returncode == 0 and gr.returncode == 0 else "FAIL",
        "gates": red[0] if red else f"gates exit {gr.returncode}",
        "selftest": ("all 6 proven red-able on their own historical defect"
                     if st.returncode == 0 else "AT LEAST ONE GATE IS VACUOUS"),
        "detail": "G1..G6 all green AND all proven red-able (scripts/v1_retire/gates.py)",
    }

    d["overall"] = ("v1 IS DEAD"
                    if all(d[k]["state"] == "PASS"
                           for k in ("d1", "d2", "d3", "d4", "d5", "d6", "d7", "d8"))
                    else "v1 IS ALIVE")
    return d


def render(d: dict) -> None:
    mark = {"PASS": "PASS", "FAIL": "FAIL", UNKNOWN: "????"}
    print("V1 RETIREMENT RUN-STATE — derived, never typed")
    print("=" * 66)
    c = d["catalogue"]
    if c.get("total") != UNKNOWN:
        print(f"catalogue: {c['total']} tools = {c['live']} live + {c['legacy']} legacy")
    print()

    for key, title in (("d1", "D1  the construct is gone"),
                       ("d2", "D2  nothing chat-service-local reaches the model"),
                       ("d3", "D3  the manifest declaration's owner is a domain service"),
                       ("d4", "D4  the tasks gate is total where a task is possible"),
                       ("d5", "D5  deprecated is dead to the model UNAIDED"),
                       ("d6", "D6  no document describes v1 as current"),
                       ("d7", "D7  regression is impossible, not merely unlikely"),
                       ("d8", "D8  every service this loop touched still IMPORTS")):
        row = d[key]
        print(f"[{mark.get(row['state'], '????')}] {title}")
        for k, v in row.items():
            if k in ("state", "detail", "sites") or not v:
                continue
            print(f"        {k}: {v}")
        if row.get("detail"):
            print(f"        -> {row['detail']}")
        print()

    ct = d["contract"]
    print(f"contract  browser-tools.contract.json: {ct['total_entries']} entries "
          f"({len(ct['v1_entries'])} v1, {len(ct['migrated_entries'])} already migrated)")
    if ct["v1_entries"]:
        print(f"        v1: {', '.join(ct['v1_entries'])}")
    print()
    print("=" * 66)
    print(f"OVERALL: {d['overall']}")
    if d["d4"]["state"] == "FAIL":
        print("\nungated confirm-mint sites (D4):")
        for svc, sites in d["d4"]["sites"].items():
            print(f"  {svc} ({len(sites)})")
            for s in sites:
                print(f"      {s}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 while v1 is not dead (for CI)")
    a = ap.parse_args()
    d = collect()
    if a.json:
        print(json.dumps(d, indent=2, ensure_ascii=False))
    else:
        render(d)
    # 🔴 The exit code MATCHES the verdict. The audit found problem_remaining.py printing
    # "STOPPING IS NOT YET LEGITIMATE" and exiting 0 — a green CI over a printed refusal is how
    # 13 unwritten invariants stayed invisible. Never separate the two again.
    if a.check:
        return 1 if d["overall"] != "v1 IS DEAD" else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
