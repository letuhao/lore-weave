"""Validate NovelSystemSpec against golden expectations and linter rules."""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import yaml

# D-PLANFORGE-PA-REALM-FALSE-POSITIVE: matches PA-scales-WITH-realm phrasing
# ("theo cảnh giới", "tỷ lệ với cảnh giới", ...) -- NOT a bare "cảnh giới"
# mention, which also fires on legitimate one-time realm-breakthrough triggers.
_REALM_COUPLING_PATTERN = re.compile(
    r"(theo|tỷ lệ (với|thuận với)|dựa (trên|vào)|gắn (với|liền với)|mỗi)\s+"
    r"(cấp (độ|bậc)\s+)?cảnh giới"
)

def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, val in patch.items():
        if key in out and isinstance(out[key], list) and isinstance(val, list):
            if val and isinstance(val[0], dict) and "id" in val[0]:
                by_id = {item["id"]: item for item in out[key] if isinstance(item, dict) and "id" in item}
                for item in val:
                    if "id" in item:
                        by_id[item["id"]] = {**by_id.get(item["id"], {}), **item}
                out[key] = list(by_id.values())
            else:
                out[key] = val
        elif key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = {**out[key], **val}
        else:
            out[key] = val
    return out


def run_rules(spec: dict[str, Any], package: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    # D-PLANFORGE-GENERAL-VALIDATE: this whole module started as the POC's OWN
    # golden-fixture acceptance test (validate_golden below) and its `run_rules`
    # got reused directly as the LIVE per-user validate()/compile() gate without
    # ever being generalized. The 4 rules below hard-require the ORIGINAL POC
    # story's own specifics (its PA/HA/CD/THR variable framework, its arc_2
    # discovery-kind arc, its >=6 open-questions checklist) -- for any other
    # user's story these are usually meaningless, so they're demoted to
    # "advisory" (reported, never blocking) rather than changing their pass/
    # fail condition (which would break the golden negative-tests below that
    # intentionally assert these SAME conditions on the fixture). A genuinely
    # general validator (structural checks that apply to any novel-system
    # spec) is real follow-up work, not a same-session rewrite.
    variables = spec.get("layers", {}).get("variables", [])
    codes = {v["code"] for v in variables}
    ok_vars = codes >= {"PA", "HA", "CD", "THR"}
    results.append(
        {"rule": "vars_four", "pass": ok_vars, "detail": f"codes={sorted(codes)}", "tier": "advisory"}
    )

    pa_not_realm = True
    for ev in spec.get("events", []):
        for d in ev.get("var_deltas", []):
            if not isinstance(d, dict):
                continue
            if d.get("coupled_to_realm"):
                pa_not_realm = False
            reason_lower = d.get("reason", "").lower()
            # D-PLANFORGE-PA-REALM-FALSE-POSITIVE: a bare "cảnh giới" mention
            # is NOT proof of forbidden coupling -- live-audited against 5 real
            # LLM propose runs, EVERY one described the Tiểu Thành realm-entry
            # event's PA trigger by naming the realm breakthrough itself (e.g.
            # "Đột phá cảnh giới đầu tiên"), which the story's own design
            # explicitly sanctions (a one-time perfection EXPERIENCE, not
            # scaling). Only flag language that describes PA moving
            # PROPORTIONALLY WITH/BY realm ("theo cảnh giới" etc.) -- the
            # exact phrase the source doc itself uses for the forbidden case
            # ("PA... không tăng/giảm theo cảnh giới").
            if d.get("variable") == "PA" and _REALM_COUPLING_PATTERN.search(reason_lower):
                pa_not_realm = False
    # ADVISORY (27 V2-G). This rule is about ONE novel's `PA` variable and its one forbidden
    # coupling. For any book that does not declare a `PA`, it passes VACUOUSLY — there are no PA
    # deltas to inspect — so as a hard compile gate it was pure theatre: it could only ever block the
    # POC, and only for a mistake the POC's own author defined.
    results.append({"rule": "pa_not_realm", "pass": pa_not_realm, "detail": "", "tier": "advisory"})

    arc2 = next((a for a in spec.get("arcs", []) if a["id"] == "arc_2"), None)
    arc2_ok = arc2 is not None and arc2.get("arc_kind") == "discovery"
    results.append(
        {
            "rule": "arc2_discovery",
            "pass": arc2_ok,
            "detail": arc2.get("theme", "") if arc2 else "missing",
            "tier": "advisory",
        }
    )

    # ADVISORY (27 V2-G) — this was the last fixture rule still GATING compile, and it blocked every
    # book with a shorter charter than the POC's from compiling at all.
    #
    # `>= 4` is not a general truth about novels; it is the POC's own anchor count, rounded down. A
    # braindump that names two things about its protagonist is a perfectly legitimate plan — and the
    # `cast` pass exists precisely to propose more. Reporting a thin charter is useful; REFUSING to
    # compile it is the tool overruling the author about their own book.
    #
    # (PF-8's rationale says it plainly: spec writes need no human gate — the heavy gate guards the
    # manuscript and the glossary. A compile that materialises nothing is caught by E4 at the link
    # step, which is a structural fact, not a taste judgement.)
    anchors = spec.get("charter", {}).get("consistency_anchors", [])
    results.append(
        {
            "rule": "anchors_min",
            "pass": len(anchors) >= 4,
            "detail": f"count={len(anchors)}",
            "tier": "advisory",
        }
    )

    # ── the genuinely GENERAL hard gates ─────────────────────────────────────────────────────
    # What actually makes a package unusable, for any novel, in any language: nothing to compile.
    # This is E4/PF-8's "zero nodes linked ⇒ error" law applied one layer earlier, where the user
    # can still do something about it — and it is the ONLY thing rules-mode compile now blocks on.
    arcs = spec.get("arcs") or []
    events = spec.get("events") or []
    results.append({
        "rule": "spec_has_arc",
        "pass": bool(arcs),
        "detail": (
            f"arcs={len(arcs)}" if arcs else
            "no arcs parsed — an arc is a '## ' heading inside the Arc Overview section"
        ),
    })
    results.append({
        "rule": "spec_has_events",
        "pass": bool(events),
        "detail": (
            f"events={len(events)}" if events else
            "no events parsed — an event is a '### ' heading inside an arc"
        ),
    })
    # F-5 governance — GENERALITY guard: `spec_has_events` only checks the TOTAL count, so a spec
    # that concentrates every event in ONE arc (the exact defect a POC-welded prompt produces —
    # "Arc 2 MUST have 7 events" → arc_1/arc_3 empty) passes it, and then compiling any OTHER arc
    # materialises nothing (E4's 400). Compile is per-arc, so this is ADVISORY (compiling the
    # populated arc still works) but it MUST surface: an author picks an arc by title and cannot
    # know it is empty, and the repair loop (autofix) needs the signal to redistribute. Names the
    # empty arcs so the fix is targeted, not "somewhere an arc is empty".
    arc_ids = [a.get("id") for a in arcs if a.get("id")]
    ev_by_arc = {aid: 0 for aid in arc_ids}
    for ev in events:
        aid = ev.get("arc_id")
        if aid in ev_by_arc:
            ev_by_arc[aid] += 1
    empty_arcs = [aid for aid in arc_ids if ev_by_arc.get(aid, 0) == 0]
    results.append({
        "rule": "every_arc_has_events",
        "pass": not empty_arcs,
        "detail": (
            f"per-arc events: {ev_by_arc}" if not empty_arcs else
            f"arcs with NO events (cannot be compiled): {empty_arcs} — every arc's events must "
            f"carry that arc's id; distribute events across all arcs, never one"
        ),
        "tier": "advisory",
    })

    thr_fail = False
    for ev in spec.get("events", []):
        arc = ev.get("arc_id", "")
        if arc not in ("arc_2", "transition") and not str(ev.get("id", "")).startswith("arc_2"):
            continue
        syn = (ev.get("synopsis") or "").lower()
        if "thr" in syn and ("giải thích" in syn or "được giải thích" in syn):
            thr_fail = True
        if "tiền kiếp" in syn and "giải thích" in syn:
            thr_fail = True
    results.append(
        {"rule": "thr_no_early_explain", "pass": not thr_fail, "detail": "", "tier": "advisory"}
    )

    open_q = spec.get("meta", {}).get("open_questions", [])
    results.append(
        {
            "rule": "open_questions_preserved",
            "pass": len(open_q) >= 6,
            "detail": f"count={len(open_q)}",
            "tier": "advisory",
        }
    )

    if package:
        plen = len(package.get("premise", ""))
        results.append(
            {
                "rule": "premise_max",
                "pass": plen <= 4000,
                "detail": f"chars={plen}",
            }
        )

    notes_total = 0
    notes_linked = 0
    for e in spec.get("events", []):
        if e.get("arc_id") != "arc_2":
            continue
        notes = e.get("planner_notes", [])
        if isinstance(notes, str):
            notes = [notes] if notes.strip() else []
        notes_total += len(notes)
        for _ in notes:
            if any(l.get("from") == e["id"] for l in spec.get("links", [])):
                notes_linked += 1
    ratio = notes_linked / notes_total if notes_total else 1.0
    results.append(
        {
            "rule": "notes_linked",
            "pass": ratio >= 0.8,
            "detail": f"ratio={ratio:.2f}",
        }
    )

    # D-PLANFORGE-STORY-GRID-POC (2026-07-06): 8th rule, ADVISORY tier only.
    # Adopted after cross-method live-LLM evaluation (see
    # docs/eval/plan-forge-story-grid-poc-2026-07-06.md) found a real,
    # cross-method-validated gap this signal alone catches. Tagged
    # "tier": "advisory" -- callers that hard-gate on run_rules() (validate(),
    # compile() in plan_forge_service.py) MUST filter to tier=="hard" (the
    # default for every rule above) before treating a FAIL as blocking. This
    # rule is intentionally noisy per-event (a single-fixture cross-method
    # audit showed some events flip between generation methods) -- never
    # promote it to hard tier without re-running that audit.
    arc2_events = [e for e in spec.get("events", []) if e.get("arc_id") == "arc_2"]
    no_value_shift = [e["id"] for e in arc2_events if not e.get("var_deltas") and e.get("id")]
    results.append(
        {
            "rule": "sg_value_shift_per_scene",
            "pass": not no_value_shift,
            "detail": (
                f"events_without_value_shift={no_value_shift}"
                if no_value_shift
                else f"checked={len(arc2_events)}"
            ),
            "tier": "advisory",
        }
    )

    return results


def validate_golden(
    spec: dict[str, Any],
    package: dict[str, Any],
    graph: dict[str, Any],
    doc: dict[str, Any],
    golden_path: Path,
) -> dict[str, Any]:
    golden = yaml.safe_load(golden_path.read_text(encoding="utf-8"))
    rule_results = run_rules(spec, package)

    section_kinds = {s["kind"] for s in doc.get("sections", [])}
    required = set(golden["sections"]["required_kinds"])
    s1_pass = required <= section_kinds and len(doc.get("sections", [])) >= golden["sections"]["count"]

    arc2_events = [e for e in spec.get("events", []) if e.get("arc_id") == "arc_2"]
    s5_pass = len(arc2_events) >= golden["arcs"]["arc2"]["min_events"]

    negative: list[dict[str, Any]] = []
    for neg in golden.get("negative_tests", []):
        patched = _deep_merge(spec, neg.get("patch", {}))
        patched_rules = run_rules(patched, package)
        failed_expected = {
            r["rule"] for r in patched_rules if not r["pass"]
        }
        expect = set(neg.get("expect_fail_rules", []))
        negative.append(
            {
                "id": neg["id"],
                "pass": bool(expect & failed_expected),
                "failed_rules": sorted(failed_expected),
                "expected": sorted(expect),
            }
        )

    neg_types = sum(1 for n in negative if n["pass"])
    s8_pass = neg_types >= 3

    criteria = {
        "S1": s1_pass,
        "S2": all(r["pass"] for r in rule_results if r["rule"] == "vars_four"),
        "S3": any(r["pass"] for r in rule_results if r["rule"] == "anchors_min"),
        # S4 (`arc2_discovery`) is NOT a criterion any more — 27 V2-G.
        #
        # It asserted `spec.arcs["arc_2"].arc_kind == "discovery"` — a value the PROPOSER used to
        # HARDCODE. So the validator was checking the fixture against itself: the rule could not
        # fail, for any document, because the thing it validated was a constant. A tautology dressed
        # as a golden criterion.
        #
        # Now that the proposer parses instead of fabricating, `arc_kind` is populated only when the
        # author states one, and this document never does — it says what kind of arc it is in prose
        # ("this is not a power arc; it is a discovery-and-price arc"), which is now carried
        # faithfully in the arc's summary and reaches the premise. So the INFORMATION survives; what
        # is gone is the pretence that a general validator could grade every book on whether its
        # second arc is a "discovery" arc.
        #
        # The rule itself stays, `tier: advisory`, exactly as 27 PF-19 says the four fixture rules
        # should — reported, never gating.
        "S5": s5_pass and any(r["pass"] for r in rule_results if r["rule"] == "notes_linked"),
        "S6": any(r["pass"] for r in rule_results if r["rule"] == "premise_max"),
        "S7": len(spec.get("layers", {}).get("variables", [])) == 4,
        "S8": s8_pass,
    }

    return {
        "criteria": criteria,
        "all_pass": all(criteria.values()),
        "rules": rule_results,
        "negative_tests": negative,
        "graph_stats": graph.get("stats", {}),
    }


def format_report(validation: dict[str, Any]) -> str:
    lines = ["# PlanForge POC Validation Report", ""]
    lines.append(f"**Overall:** {'PASS' if validation['all_pass'] else 'FAIL'}")
    lines.append("")
    lines.append("## Success criteria")
    lines.append("")
    lines.append("| ID | Pass |")
    lines.append("|----|------|")
    for k, v in validation["criteria"].items():
        lines.append(f"| {k} | {'✓' if v else '✗'} |")
    lines.append("")
    lines.append("## Linter rules")
    lines.append("")
    for r in validation["rules"]:
        status = "PASS" if r["pass"] else "FAIL"
        lines.append(f"- `{r['rule']}`: {status} — {r.get('detail', '')}")
    lines.append("")
    lines.append("## Negative tests")
    lines.append("")
    for n in validation["negative_tests"]:
        status = "PASS" if n["pass"] else "FAIL"
        lines.append(f"- `{n['id']}`: {status} (failed: {n['failed_rules']})")
    lines.append("")
    if validation["all_pass"]:
        lines.append("**Recommendation:** Promote engine to `composition-service/app/engine/plan_forge/` after review.")
    else:
        lines.append("**Recommendation:** Iterate on propose/link rules before promote.")
    return "\n".join(lines)
