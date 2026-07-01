"""Human-in-the-loop surgical refine for PlanAnalyze and NovelSystemSpec."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any

from app.engine.plan_forge.json_extract import extract_json_object
from app.engine.plan_forge.llm_client import LMStudioClient
from app.engine.plan_forge.prompts import (
    REFINE_ANALYZE_SYSTEM,
    REFINE_SPEC_SYSTEM,
    refine_user_prompt,
    repair_user_prompt,
)
from app.engine.plan_forge.propose_llm import normalize_spec
from app.engine.plan_forge.spec_index import spec_slice_for_paths
from app.engine.plan_forge.validate import run_rules


def artifact_json_for_refine(spec: dict[str, Any], revision: dict[str, Any]) -> str:
    paths = revision.get("focus_paths") or []
    if paths:
        return spec_slice_for_paths(spec, paths, max_chars=12000)
    return json.dumps(spec, ensure_ascii=False, indent=2)


def _is_full_novel_system_spec(doc: dict[str, Any]) -> bool:
    return isinstance(doc.get("layers"), dict) and "events" in doc and "arcs" in doc


def merge_refine_output(before: dict[str, Any], patch: dict[str, Any], revision: dict[str, Any]) -> dict[str, Any]:
    """Merge a slice-shaped LLM patch into the full spec when focus_paths is set."""
    paths = revision.get("focus_paths") or []
    if not paths or _is_full_novel_system_spec(patch):
        return patch
    out = copy.deepcopy(before)
    for p in paths:
        if p.startswith("events["):
            eid = p.split("[", 1)[1].rstrip("]")
            new_ev = patch.get(p)
            if new_ev is None and isinstance(patch.get("events"), list):
                new_ev = next((e for e in patch["events"] if e.get("id") == eid), None)
            if new_ev is None:
                continue
            events = out.setdefault("events", [])
            for i, e in enumerate(events):
                if e.get("id") == eid:
                    events[i] = new_ev
                    break
        elif p == "layers.characters[0]":
            val = patch.get(p)
            if val is None:
                chars = (patch.get("layers") or {}).get("characters") or []
                val = chars[0] if chars else None
            if val is None:
                continue
            layers = out.setdefault("layers", {})
            chars = layers.setdefault("characters", [])
            if chars:
                chars[0] = val
            else:
                chars.append(val)
        elif p.startswith("layers.mechanics"):
            mid = p.split("[", 1)[1].rstrip("]") if "[" in p else ""
            new_m = patch.get(p)
            if new_m is None:
                for m in (patch.get("layers") or {}).get("mechanics") or []:
                    if m.get("id") == mid:
                        new_m = m
                        break
            if new_m is None:
                continue
            mechanics = out.setdefault("layers", {}).setdefault("mechanics", [])
            for i, m in enumerate(mechanics):
                if m.get("id") == mid:
                    mechanics[i] = new_m
                    break
    return out


@dataclass
class AcceptResult:
    accepted: bool
    reasons: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)


def _parse_with_repair(
    client: LMStudioClient,
    step: str,
    system: str,
    user: str,
    repair_step: str,
    *,
    temperature: float = 0.1,
) -> dict[str, Any]:
    content = client.chat(step=step, system=system, user=user, temperature=temperature)
    try:
        return extract_json_object(content)
    except (json.JSONDecodeError, ValueError) as e:
        repair_content = client.chat(
            step=repair_step,
            system="Output only valid JSON. No markdown.",
            user=repair_user_prompt(str(e), content),
            max_tokens=12000,
            temperature=temperature,
        )
        return extract_json_object(repair_content)


def _get_path_value(obj: dict[str, Any], path: str) -> Any:
    if path in obj:
        return copy.deepcopy(obj[path])
    if "." in path:
        cur: Any = obj
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
        return copy.deepcopy(cur)
    if path == "variables":
        if "variables" in obj:
            return copy.deepcopy(obj["variables"])
        return copy.deepcopy(obj.get("layers", {}).get("variables", []))
    if path == "arcs":
        return copy.deepcopy(obj.get("arcs", []))
    return None


def _arc2_kind(arcs: list[dict[str, Any]] | None) -> Any:
    if not arcs:
        return None
    for a in arcs:
        if a.get("id") == "arc_2":
            return a.get("arc_kind")
    return None


def _variable_codes(obj: dict[str, Any]) -> list[str]:
    vars_ = _get_path_value(obj, "variables")
    if not isinstance(vars_, list):
        return []
    return sorted(v.get("code", "") for v in vars_ if isinstance(v, dict) and v.get("code"))


def frozen_paths_intact(before: dict[str, Any], after: dict[str, Any], frozen_paths: list[str]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for fp in frozen_paths:
        if fp in ("variables", "variables[*].code"):
            if _variable_codes(before) != _variable_codes(after):
                failures.append(f"variable codes changed: {fp}")
        elif fp == "arcs" or fp.startswith("arcs["):
            b_arcs = _get_path_value(before, "arcs") or []
            a_arcs = _get_path_value(after, "arcs") or []
            if _arc2_kind(b_arcs) != _arc2_kind(a_arcs):
                failures.append("arc_2 arc_kind changed")
            b_ids = {a.get("id") for a in b_arcs if isinstance(a, dict)}
            a_ids = {a.get("id") for a in a_arcs if isinstance(a, dict)}
            if b_ids - a_ids:
                failures.append("arcs removed")
        elif fp == "charter.forbids":
            b = (before.get("charter") or {}).get("forbids")
            a = (after.get("charter") or {}).get("forbids")
            if b != a:
                failures.append("charter.forbids changed")
        else:
            bv = _get_path_value(before, fp)
            av = _get_path_value(after, fp)
            if bv != av:
                failures.append(f"frozen path changed: {fp}")
    return (len(failures) == 0, failures)


def _rule_pass_map(rules: list[dict[str, Any]]) -> dict[str, bool]:
    return {r["rule"]: r["pass"] for r in rules}


CORE_RULES = ("vars_four", "arc2_discovery", "thr_no_early_explain", "notes_linked")


def linter_no_regress(before_rules: list[dict[str, Any]], after_rules: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    b = _rule_pass_map(before_rules)
    a = _rule_pass_map(after_rules)
    failures: list[str] = []
    for name in CORE_RULES:
        if b.get(name) and not a.get(name):
            failures.append(f"regressed rule: {name}")
    return (len(failures) == 0, failures)


def open_questions_ok(before: dict[str, Any], after: dict[str, Any]) -> tuple[bool, str]:
    def _oq(obj: dict[str, Any]) -> list[str]:
        if "open_questions" in obj:
            return list(obj.get("open_questions") or [])
        return list((obj.get("meta") or {}).get("open_questions") or [])

    bq, aq = _oq(before), _oq(after)
    if len(aq) < len(bq):
        return False, f"open_questions shrank {len(bq)} -> {len(aq)}"
    return True, ""


def expect_contains_ok(after: dict[str, Any], revision: dict[str, Any]) -> tuple[bool, list[str]]:
    blob = json.dumps(after, ensure_ascii=False).lower()
    missing: list[str] = []
    for token in revision.get("expect_contains") or []:
        if token.lower() not in blob:
            missing.append(token)
    for token in _instruction_tokens(revision.get("instruction", "")):
        if token.lower() not in blob:
            missing.append(token)
    return (len(missing) == 0, missing)


def _instruction_tokens(instruction: str) -> list[str]:
    tokens: list[str] = []
    if "thử nghiệm" in instruction.lower():
        tokens.append("Thử Nghiệm")
    return tokens


def arc2_event_titles(spec: dict[str, Any]) -> list[str]:
    return [e.get("title", "") for e in spec.get("events", []) if e.get("arc_id") == "arc_2"]


def anchor_jaccard(before: dict[str, Any], after: dict[str, Any]) -> float:
    def _anchors(obj: dict[str, Any]) -> set[str]:
        if "consistency_anchors" in obj:
            return set(obj.get("consistency_anchors") or [])
        return set((obj.get("charter") or {}).get("consistency_anchors") or [])

    b, a = _anchors(before), _anchors(after)
    if not b and not a:
        return 1.0
    union = b | a
    return len(b & a) / len(union) if union else 1.0


def events_removed_outside_scope(
    before: dict[str, Any],
    after: dict[str, Any],
    scope: list[str],
) -> list[str]:
    if "events" in scope:
        return []
    b_titles = {e.get("title") for e in before.get("events", []) if e.get("arc_id") == "arc_2"}
    a_titles = {e.get("title") for e in after.get("events", []) if e.get("arc_id") == "arc_2"}
    return sorted(t for t in b_titles - a_titles if t)


def _trait_count(obj: dict[str, Any]) -> int:
    if "layers" in obj:
        chars = (obj.get("layers") or {}).get("characters") or []
        if chars:
            return len(chars[0].get("traits") or [])
    return len(obj.get("consistency_anchors") or [])


def _arc2_event_count(obj: dict[str, Any]) -> int:
    return len([e for e in obj.get("events", []) if e.get("arc_id") == "arc_2"])


def _is_spec_artifact(obj: dict[str, Any]) -> bool:
    return "layers" in obj or ("charter" in obj and "meta" in obj)


def accept_refine(
    before: dict[str, Any],
    after: dict[str, Any],
    revision: dict[str, Any],
    *,
    package: dict[str, Any] | None = None,
    criteria_before: dict[str, bool] | None = None,
    criteria_after: dict[str, bool] | None = None,
    fidelity_cfg: dict[str, Any] | None = None,
    fidelity_before: float | None = None,
    fidelity_after: float | None = None,
) -> AcceptResult:
    reasons: list[str] = []
    checks: dict[str, bool] = {}

    frozen_ok, frozen_fail = frozen_paths_intact(before, after, revision.get("frozen_paths") or [])
    checks["M3_frozen_paths"] = frozen_ok
    if not frozen_ok:
        reasons.extend(frozen_fail)

    br = run_rules(before, package) if _is_spec_artifact(before) else []
    ar = run_rules(after, package) if _is_spec_artifact(after) else []
    if br and ar:
        lint_ok, lint_fail = linter_no_regress(br, ar)
        checks["M2_linter"] = lint_ok
        if not lint_ok:
            reasons.extend(lint_fail)
    else:
        checks["M2_linter"] = True

    if criteria_before and criteria_after:
        for k, bv in criteria_before.items():
            if bv and not criteria_after.get(k):
                checks[f"M1_{k}"] = False
                reasons.append(f"golden criterion regressed: {k}")
            else:
                checks[f"M1_{k}"] = True
    else:
        checks["M1_golden"] = True

    oq_ok, oq_msg = open_questions_ok(before, after)
    checks["M4_open_questions"] = oq_ok
    if not oq_ok:
        reasons.append(oq_msg)

    exp_ok, exp_missing = expect_contains_ok(after, revision)
    checks["D1_target"] = exp_ok
    if not exp_ok:
        reasons.append(f"expected tokens missing: {exp_missing}")

    removed = events_removed_outside_scope(before, after, revision.get("scope") or [])
    checks["C1_no_event_removal"] = len(removed) == 0
    if removed:
        reasons.append(f"events removed outside scope: {removed}")

    if "consistency_anchors" not in (revision.get("scope") or []) and "charter" not in (revision.get("scope") or []):
        j = anchor_jaccard(before, after)
        checks["C2_anchor_jaccard"] = j >= 0.8
        if j < 0.8:
            reasons.append(f"anchor churn jaccard={j:.2f}")

    b_notes = next((r for r in br if r["rule"] == "notes_linked"), {}) if br else {}
    a_notes = next((r for r in ar if r["rule"] == "notes_linked"), {}) if ar else {}
    if br:
        checks["C3_notes_linked"] = a_notes.get("pass", False) or (
            b_notes.get("pass", False) and a_notes.get("pass", False)
        )
        if b_notes.get("pass") and not a_notes.get("pass"):
            reasons.append("notes_linked regressed")
    else:
        checks["C3_notes_linked"] = True

    if fidelity_before is not None and fidelity_after is not None:
        checks["F1_fidelity_monotonic"] = fidelity_after >= fidelity_before
        if fidelity_after < fidelity_before:
            reasons.append(f"fidelity regressed {fidelity_before:.3f} -> {fidelity_after:.3f}")

    tc_before, tc_after = _trait_count(before), _trait_count(after)
    checks["F2_trait_count"] = tc_after >= tc_before
    if tc_after < tc_before:
        reasons.append(f"trait count shrank {tc_before} -> {tc_after}")

    ec_before, ec_after = _arc2_event_count(before), _arc2_event_count(after)
    checks["F3_arc2_events"] = ec_after >= ec_before
    if ec_after < ec_before and "events" not in (revision.get("scope") or []):
        reasons.append(f"arc_2 events shrank {ec_before} -> {ec_after}")

    return AcceptResult(accepted=len(reasons) == 0, reasons=reasons, checks=checks)


def refine_analyze(
    analyze: dict[str, Any],
    revision: dict[str, Any],
    *,
    client: LMStudioClient,
) -> dict[str, Any]:
    revision = {**revision, "target": "analyze"}
    payload = refine_user_prompt(json.dumps(analyze, ensure_ascii=False, indent=2), revision)
    out = _parse_with_repair(client, "refine_analyze", REFINE_ANALYZE_SYSTEM, payload, "refine_analyze_repair")
    out.setdefault("version", 1)
    return out


def refine_spec(
    spec: dict[str, Any],
    revision: dict[str, Any],
    *,
    client: LMStudioClient,
    source_checksum: str,
    analyze: dict[str, Any] | None = None,
) -> dict[str, Any]:
    revision = {**revision, "target": "spec"}
    payload = refine_user_prompt(artifact_json_for_refine(spec, revision), revision)
    out = _parse_with_repair(client, "refine_spec", REFINE_SPEC_SYSTEM, payload, "refine_spec_repair")
    merged = merge_refine_output(spec, out, revision)
    return normalize_spec(merged, source_checksum, analyze=analyze)


def apply_refine_if_accepted(
    before: dict[str, Any],
    candidate: dict[str, Any],
    revision: dict[str, Any],
    **accept_kw: Any,
) -> tuple[dict[str, Any], AcceptResult]:
    result = accept_refine(before, candidate, revision, **accept_kw)
    if result.accepted:
        return candidate, result
    return before, result
