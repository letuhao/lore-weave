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
    variables = spec.get("layers", {}).get("variables", [])
    codes = {v["code"] for v in variables}
    ok_vars = codes >= {"PA", "HA", "CD", "THR"}
    results.append({"rule": "vars_four", "pass": ok_vars, "detail": f"codes={sorted(codes)}"})

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
    results.append({"rule": "pa_not_realm", "pass": pa_not_realm, "detail": ""})

    arc2 = next((a for a in spec.get("arcs", []) if a["id"] == "arc_2"), None)
    arc2_ok = arc2 is not None and arc2.get("arc_kind") == "discovery"
    results.append(
        {
            "rule": "arc2_discovery",
            "pass": arc2_ok,
            "detail": arc2.get("theme", "") if arc2 else "missing",
        }
    )

    anchors = spec.get("charter", {}).get("consistency_anchors", [])
    results.append(
        {
            "rule": "anchors_min",
            "pass": len(anchors) >= 4,
            "detail": f"count={len(anchors)}",
        }
    )

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
    results.append({"rule": "thr_no_early_explain", "pass": not thr_fail, "detail": ""})

    open_q = spec.get("meta", {}).get("open_questions", [])
    results.append(
        {
            "rule": "open_questions_preserved",
            "pass": len(open_q) >= 6,
            "detail": f"count={len(open_q)}",
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
        "S4": any(r["pass"] for r in rule_results if r["rule"] == "arc2_discovery"),
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
