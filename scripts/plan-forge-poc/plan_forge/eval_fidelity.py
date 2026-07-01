"""Fidelity rubric evaluation for PlanForge POC."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml


def load_fidelity_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _norm(text: str) -> str:
    return text.lower().strip()


def _blob(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False).lower()


def _arc2_events(obj: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in obj.get("events", []) if e.get("arc_id") == "arc_2"]


def _character_layer(spec: dict[str, Any]) -> dict[str, Any] | None:
    chars = (spec.get("layers") or {}).get("characters") or []
    return chars[0] if chars else None


def _mechanics(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return list((spec.get("layers") or {}).get("mechanics") or [])


def _check_keyword_any(text: str, keywords: list[str]) -> bool:
    t = _norm(text)
    return any(k.lower() in t for k in keywords)


def _vn_char_ratio(text: str) -> float:
    if not text:
        return 0.0
    vn = len(re.findall(r"[\u00C0-\u1EF9]", text))
    return vn / max(len(text), 1)


def _check_polish(spec: dict[str, Any], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    polish = cfg.get("polish") or {}
    char = _character_layer(spec) or {}

    if polish.get("baseline_notes_must_be_vn"):
        notes = char.get("baseline_notes") or ""
        ratio = _vn_char_ratio(notes)
        min_ratio = polish.get("min_baseline_notes_vn_ratio", 0.35)
        checks.append(
            {
                "id": "polish_baseline_notes_vn",
                "pass": _has_vietnamese(notes) and ratio >= min_ratio,
                "detail": f"vn_ratio={ratio:.2f} need>={min_ratio}",
            }
        )

    name = (char.get("name") or "").strip()
    blocked = [b.lower() for b in polish.get("character_name_blocked") or []]
    if blocked:
        bad = any(b in name.lower() for b in blocked) if name else True
        checks.append(
            {
                "id": "polish_character_name",
                "pass": not bad and bool(name),
                "detail": f"name={name!r}",
            }
        )

    min_vn_ratio = polish.get("mechanic_rules_min_vn_ratio", 0.5)
    all_rules: list[str] = []
    for m in _mechanics(spec):
        all_rules.extend(m.get("rules") or [])
    if all_rules:
        vn_rules = sum(1 for r in all_rules if _has_vietnamese(r))
        ratio = vn_rules / len(all_rules)
        checks.append(
            {
                "id": "polish_mechanic_rules_vn",
                "pass": ratio >= min_vn_ratio,
                "detail": f"vn_rules={vn_rules}/{len(all_rules)} ratio={ratio:.2f}",
            }
        )

    events = _arc2_events(spec)
    for rule in polish.get("event_bullet_coverage") or []:
        title_match = rule.get("title_match", "")
        ev = _event_by_title(events, title_match)
        keywords = rule.get("keywords") or []
        min_hits = rule.get("min_keyword_hits", 3)
        if not ev:
            checks.append(
                {
                    "id": f"polish_bullets_{title_match[:8]}",
                    "pass": False,
                    "detail": f"missing {title_match}",
                }
            )
            continue
        combined = _norm((ev.get("synopsis") or "") + " " + (ev.get("goal") or ""))
        hits = sum(1 for k in keywords if k.lower() in combined)
        checks.append(
            {
                "id": f"polish_bullets_{title_match[:8]}",
                "pass": hits >= min_hits,
                "detail": f"{title_match}: hits={hits} need>={min_hits}",
            }
        )
    return checks


def _check_trait_keywords(spec: dict[str, Any], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    char_cfg = cfg.get("character") or {}
    char = _character_layer(spec)
    traits = list(char.get("traits") or []) if char else []
    anchors = list((spec.get("charter") or {}).get("consistency_anchors") or [])
    trait_blob = " ".join(traits + anchors)

    min_traits = char_cfg.get("min_trait_count", 5)
    ok_count = len(traits) >= min_traits
    checks.append(
        {
            "id": "char_trait_count",
            "pass": ok_count,
            "detail": f"traits={len(traits)} need>={min_traits}",
        }
    )

    for kw in char_cfg.get("required_trait_keywords") or []:
        ok = kw.lower() in _norm(trait_blob)
        checks.append({"id": f"char_trait_{kw[:12]}", "pass": ok, "detail": f"keyword={kw}"})

    notes = (char or {}).get("baseline_notes") or ""
    min_notes = char_cfg.get("min_baseline_notes_chars", 200)
    checks.append(
        {
            "id": "char_baseline_notes_len",
            "pass": len(notes) >= min_notes,
            "detail": f"len={len(notes)} need>={min_notes}",
        }
    )

    notes_blob = _norm(notes + " " + trait_blob)
    for kw in char_cfg.get("required_mundane_mentions") or []:
        checks.append(
            {
                "id": f"char_mundane_{kw[:8]}",
                "pass": kw.lower() in notes_blob,
                "detail": f"mention={kw}",
            }
        )
    return checks


def _check_mechanics(spec: dict[str, Any], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    mech_cfg = cfg.get("mechanics") or {}
    mechs = _mechanics(spec)
    min_count = mech_cfg.get("min_mechanic_count", 3)
    checks.append(
        {
            "id": "mech_count",
            "pass": len(mechs) >= min_count,
            "detail": f"mechanics={len(mechs)} need>={min_count}",
        }
    )

    min_rules = mech_cfg.get("min_rules_per_mechanic", 2)
    for i, m in enumerate(mechs):
        rules = m.get("rules") or []
        checks.append(
            {
                "id": f"mech_{i}_rules",
                "pass": len(rules) >= min_rules,
                "detail": f"{m.get('name', m.get('id'))}: rules={len(rules)}",
            }
        )

    name_blob = " ".join(m.get("name", "") for m in mechs).lower()
    for kw in mech_cfg.get("required_mechanic_name_keywords") or []:
        checks.append(
            {
                "id": f"mech_name_{kw[:10]}",
                "pass": kw.lower() in name_blob or kw.lower() in _blob(spec),
                "detail": f"keyword={kw}",
            }
        )

    secret_blob = " ".join(
        s for m in mechs for s in (m.get("planner_secrets") or [])
    ).lower()
    for kw in mech_cfg.get("required_secret_keywords") or []:
        found = kw.lower() in secret_blob or kw.lower() in _blob(spec)
        checks.append({"id": f"mech_secret_{kw[:8]}", "pass": found, "detail": f"keyword={kw}"})
    return checks


def _event_by_title(events: list[dict[str, Any]], title_match: str) -> dict[str, Any] | None:
    tm = title_match.lower()
    for e in events:
        if tm in (e.get("title") or "").lower():
            return e
    return None


def _has_vietnamese(text: str) -> bool:
    return bool(re.search(r"[\u00C0-\u1EF9]", text))


def _check_arc2_events(spec: dict[str, Any], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    ev_cfg = cfg.get("arc2_events") or {}
    events = _arc2_events(spec)
    required_count = ev_cfg.get("required_count", 7)
    checks.append(
        {
            "id": "arc2_event_count",
            "pass": len(events) >= required_count,
            "detail": f"events={len(events)} need>={required_count}",
        }
    )

    titles = [e.get("title", "") for e in events]
    for req_title in ev_cfg.get("required_event_titles_vn") or []:
        ok = any(req_title.lower() in t.lower() for t in titles)
        checks.append(
            {
                "id": f"arc2_title_{req_title[:10]}",
                "pass": ok,
                "detail": f"title={req_title}",
            }
        )

    min_syn = ev_cfg.get("min_synopsis_chars", 80)
    for e in events:
        syn = e.get("synopsis") or ""
        title = e.get("title") or "event"
        checks.append(
            {
                "id": f"arc2_syn_len_{title[:12]}",
                "pass": len(syn) >= min_syn,
                "detail": f"{title}: len={len(syn)} need>={min_syn}",
            }
        )
        if ev_cfg.get("title_must_contain_vn"):
            checks.append(
                {
                    "id": f"arc2_title_vn_{title[:12]}",
                    "pass": _has_vietnamese(e.get("title") or ""),
                    "detail": f"{title}: vn_chars",
                }
            )

    for rule in ev_cfg.get("event_synopsis_checks") or []:
        title_match = rule.get("title_match", "")
        ev = _event_by_title(events, title_match)
        if not ev:
            checks.append(
                {
                    "id": f"synopsis_{title_match[:10]}",
                    "pass": False,
                    "detail": f"missing event {title_match}",
                }
            )
            continue
        syn = _norm(ev.get("synopsis") or "")
        goal = _norm(ev.get("goal") or "")
        combined = syn + " " + goal
        must_any = rule.get("must_contain_any") or []
        if must_any:
            ok = _check_keyword_any(combined, must_any)
            checks.append(
                {
                    "id": f"synopsis_{title_match[:10]}",
                    "pass": ok,
                    "detail": f"need any of {must_any}",
                }
            )
        bad_only = rule.get("must_not_contain_only") or []
        for bad in bad_only:
            if bad.lower() in combined and len(combined) < 120:
                checks.append(
                    {
                        "id": f"synopsis_not_only_{title_match[:8]}",
                        "pass": False,
                        "detail": f"too thin, only mentions {bad}",
                    }
                )
    return checks


def evaluate_spec_fidelity(spec: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.extend(_check_trait_keywords(spec, cfg))
    checks.extend(_check_mechanics(spec, cfg))
    checks.extend(_check_arc2_events(spec, cfg))
    checks.extend(_check_polish(spec, cfg))
    passed = sum(1 for c in checks if c["pass"])
    total = len(checks) or 1
    score = round(passed / total, 4)
    gate = cfg.get("gate") or {}
    gate_pass = (
        score >= gate.get("min_fidelity_score", 0.85)
        and len(_arc2_events(spec)) >= gate.get("min_arc2_events", 7)
    )
    return {
        "target": "spec",
        "score": score,
        "passed": passed,
        "total": total,
        "gate_pass": gate_pass,
        "checks": checks,
        "gaps": [c for c in checks if not c["pass"]],
    }


def evaluate_analyze_fidelity(analyze: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    a_cfg = cfg.get("analyze") or {}
    anchors = analyze.get("consistency_anchors") or []
    min_anchors = a_cfg.get("min_consistency_anchors", 4)
    checks.append(
        {
            "id": "analyze_anchors",
            "pass": len(anchors) >= min_anchors,
            "detail": f"anchors={len(anchors)}",
        }
    )

    arc2_ev = [e for e in analyze.get("events", []) if e.get("arc_id") == "arc_2"]
    min_ev = a_cfg.get("min_arc2_events_in_analyze", 7)
    checks.append(
        {
            "id": "analyze_arc2_events",
            "pass": len(arc2_ev) >= min_ev,
            "detail": f"arc2_events={len(arc2_ev)}",
        }
    )

    trait_blob = " ".join(anchors).lower()
    for kw in (cfg.get("character") or {}).get("required_trait_keywords") or []:
        checks.append(
            {
                "id": f"analyze_trait_{kw[:10]}",
                "pass": kw.lower() in trait_blob,
                "detail": f"keyword={kw}",
            }
        )

    if a_cfg.get("require_source_refs_on_events"):
        with_refs = sum(1 for e in arc2_ev if e.get("source_refs"))
        checks.append(
            {
                "id": "analyze_source_refs",
                "pass": with_refs >= min_ev,
                "detail": f"events_with_refs={with_refs}",
            }
        )

    passed = sum(1 for c in checks if c["pass"])
    total = len(checks) or 1
    return {
        "target": "analyze",
        "score": round(passed / total, 4),
        "passed": passed,
        "total": total,
        "checks": checks,
        "gaps": [c for c in checks if not c["pass"]],
    }


def evaluate_elaboration_fidelity(spec: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    e_cfg = cfg.get("elaboration") or {}
    char = _character_layer(spec) or {}
    rules = char.get("behavioral_rules") or []
    seeds = char.get("relationship_seeds") or []
    tiers = char.get("recognition_tiers") or []

    checks.append(
        {
            "id": "elab_behavioral_rules",
            "pass": len(rules) >= e_cfg.get("min_behavioral_rules", 3),
            "detail": f"rules={len(rules)}",
        }
    )
    checks.append(
        {
            "id": "elab_relationship_seeds",
            "pass": len(seeds) >= e_cfg.get("min_relationship_seeds", 2),
            "detail": f"seeds={len(seeds)}",
        }
    )
    checks.append(
        {
            "id": "elab_recognition_tiers",
            "pass": len(tiers) >= e_cfg.get("min_recognition_tiers", 4),
            "detail": f"tiers={len(tiers)}",
        }
    )

    from plan_forge.elaborate import consistency_audit

    audit = consistency_audit(spec)
    critical = audit.get("critical", [])
    checks.append(
        {
            "id": "elab_audit_critical",
            "pass": len(critical) <= e_cfg.get("max_audit_critical", 0),
            "detail": f"critical={len(critical)}",
        }
    )

    passed = sum(1 for c in checks if c["pass"])
    total = len(checks) or 1
    score = round(passed / total, 4)
    return {
        "target": "elaboration",
        "score": score,
        "passed": passed,
        "total": total,
        "gate_pass": all(c["pass"] for c in checks),
        "checks": checks,
        "gaps": [c for c in checks if not c["pass"]],
        "audit": audit,
    }


def format_fidelity_report(
    *,
    spec_result: dict[str, Any] | None = None,
    analyze_result: dict[str, Any] | None = None,
    elaboration_result: dict[str, Any] | None = None,
) -> str:
    lines = ["# PlanForge Fidelity Report", ""]
    for label, result in (
        ("Analyze", analyze_result),
        ("Spec", spec_result),
        ("Elaboration", elaboration_result),
    ):
        if not result:
            continue
        lines.append(f"## {label}")
        lines.append("")
        lines.append(f"- **Score:** {result['score']} ({result['passed']}/{result['total']})")
        if "gate_pass" in result:
            lines.append(f"- **Gate:** {'PASS' if result['gate_pass'] else 'FAIL'}")
        lines.append("")
        if result.get("gaps"):
            lines.append("### Gaps")
            lines.append("")
            for g in result["gaps"]:
                lines.append(f"- `{g['id']}`: {g['detail']}")
            lines.append("")
    return "\n".join(lines)


def suggest_fixes(gaps: list[dict[str, Any]]) -> list[str]:
    suggestions: list[str] = []
    for g in gaps:
        gid = g.get("id", "")
        if gid.startswith("char_trait"):
            suggestions.append("Bổ sung đủ 5 traits §1.3 (VN) vào layers.characters[0].traits và consistency_anchors.")
        elif gid.startswith("char_baseline"):
            suggestions.append("Mở rộng baseline_notes với §1.1–§1.3 và chi tiết mundane §1.2.")
        elif gid.startswith("arc2_title"):
            suggestions.append("Thêm event arc_2 thiếu title tiếng Việt từ source.")
        elif gid.startswith("arc2_syn_len"):
            suggestions.append("Mở rộng synopsis event — bám bullet Goal/Planner trong source.")
        elif gid.startswith("synopsis_"):
            suggestions.append(f"Sửa synopsis event: {g.get('detail')}")
        elif gid.startswith("mech_"):
            suggestions.append("Bổ sung mechanics rules/planner_secrets từ §2–§3.")
        elif gid.startswith("polish_baseline"):
            suggestions.append("Viết lại baseline_notes bằng tiếng Việt (§1.1–§1.3).")
        elif gid.startswith("polish_character"):
            suggestions.append("Đổi tên nhân vật — dùng 'Nữ chính' thay placeholder EN.")
        elif gid.startswith("polish_bullets"):
            suggestions.append("Mở rộng synopsis event với bullet từ source.")
        elif gid.startswith("polish_mechanic"):
            suggestions.append("Dịch/thêm rules mechanics sang tiếng Việt.")
    return list(dict.fromkeys(suggestions))
