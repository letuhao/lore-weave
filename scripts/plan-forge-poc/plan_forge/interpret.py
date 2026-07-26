"""Interpret vague user feedback into structured PlanRevisionRequest."""

from __future__ import annotations

import json
import re
from typing import Any

from plan_forge.json_extract import extract_json_object
from plan_forge.llm_client import LMStudioClient
from plan_forge.prompts import INTERPRET_SYSTEM, interpret_user_prompt, repair_user_prompt
from plan_forge.self_check import run_self_check
from plan_forge.spec_index import build_spec_index, search_index, spec_slice_for_paths

HANDOFF_PHRASES = (
    "làm đi",
    "sửa hết",
    "quăng cho",
    "giao cho",
    "tự sửa",
    "fix hết",
    "auto",
)
RECHECK_PHRASES = ("check lại", "xem lại", "kiểm tra", "có đúng không", "review lại")
COMPLAINT_PHRASES = ("sai", "wrong", "lỗi", "chưa đúng", "không đúng")


def detect_intent(user_message: str) -> str:
    msg = user_message.lower()
    if len(user_message) > 2000 and any(p in msg for p in HANDOFF_PHRASES):
        return "handoff"
    if any(p in msg for p in HANDOFF_PHRASES):
        return "handoff"
    if any(p in msg for p in RECHECK_PHRASES):
        return "recheck"
    if any(p in msg for p in COMPLAINT_PHRASES):
        return "complaint"
    return "clarify"


def is_lazy_handoff(user_message: str) -> bool:
    msg = user_message.lower()
    return len(user_message) > 2000 or any(p in msg for p in HANDOFF_PHRASES)


def _excerpt_for_section(section_map: list[dict[str, Any]], section_id: str) -> str:
    for s in section_map:
        if str(s.get("section_id")) == section_id:
            return (s.get("excerpt") or "")[:1500]
    for s in section_map:
        if section_id in str(s.get("section_id", "")):
            return (s.get("excerpt") or "")[:1500]
    return ""


def _gap_to_diagnosis(gap: dict[str, Any], suggestion: str) -> dict[str, Any]:
    return {
        "issue": gap.get("id", "gap"),
        "evidence": gap.get("detail", ""),
        "suggested_fix": suggestion,
        "gap_id": gap.get("id", ""),
    }


def _build_revision_from_gap(
    gap: dict[str, Any],
    focus_paths: list[str],
    section_map: list[dict[str, Any]],
    *,
    intent: str = "completeness",
) -> dict[str, Any]:
    gid = gap.get("id", "")
    instruction = f"Sửa gap fidelity: {gid}. {gap.get('detail', '')}"
    scope = ["layers", "events", "charter"]
    expect: list[str] = []
    excerpt = ""

    if gid.startswith("polish_baseline") or gid.startswith("char_baseline"):
        scope = ["layers"]
        instruction = "Viết lại baseline_notes bằng tiếng Việt, tóm tắt §1.1–§1.3, >=200 ký tự."
        expect = ["nhân vật", "linh căn"]
        excerpt = _excerpt_for_section(section_map, "1.3")
    elif "Thử" in gid or "thử" in gid.lower() or "event_3" in gid:
        scope = ["events", "links"]
        instruction = (
            "Sửa Event Thử Nghiệm: synopsis bullet gồm tốc độ tu luyện, linh thạch, "
            "âm dương khí, logic nhân vật."
        )
        expect = ["Thử Nghiệm", "linh thạch"]
        excerpt = _excerpt_for_section(section_map, "event_3")
    elif gid.startswith("polish_character"):
        scope = ["layers"]
        instruction = "Đổi name thành 'Nữ chính' — không dùng Female Protagonist."
        expect = ["Nữ chính"]
    elif gid.startswith("char_mundane"):
        scope = ["layers", "charter"]
        instruction = "Thêm chi tiết mundane (mì, mùi, cửa sổ) vào baseline_notes."
        expect = ["mì"]
        excerpt = _excerpt_for_section(section_map, "1.2")

    return {
        "version": 1,
        "target": "spec",
        "intent": intent,
        "instruction": instruction,
        "scope": scope,
        "frozen_paths": ["variables", "arcs", "charter.forbids"],
        "source_excerpt": excerpt,
        "expect_contains": expect,
    }


def interpret_rules(
    user_message: str,
    spec: dict[str, Any],
    section_map: list[dict[str, Any]],
    *,
    self_check_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    intent = detect_intent(user_message)
    index = build_spec_index(spec, section_map)
    hits = search_index(user_message, index, top_k=5)
    focus_paths = [h["path"] for h in hits if h["path"].startswith("events") or h["path"].startswith("layers")]

    gaps = (self_check_report or {}).get("ranked_gaps") or []
    suggestions = (self_check_report or {}).get("suggestions") or []

    diagnosis: list[dict[str, Any]] = []
    draft_revision: dict[str, Any] | None = None
    apply_mode = "confirm"
    clarifying: list[str] = []
    confidence = 0.5

    if intent == "recheck":
        for i, g in enumerate(gaps[:5]):
            sug = suggestions[i] if i < len(suggestions) else g.get("detail", "")
            diagnosis.append(_gap_to_diagnosis(g, sug))
        if len(gaps) == 1:
            confidence = 0.85
            apply_mode = "auto"
            draft_revision = _build_revision_from_gap(gaps[0], focus_paths, section_map, intent="recheck")
        elif gaps:
            confidence = 0.7
            draft_revision = _build_revision_from_gap(gaps[0], focus_paths, section_map, intent="recheck")
        else:
            confidence = 0.9
            apply_mode = "auto"
            diagnosis.append({"issue": "ok", "evidence": "no gaps", "suggested_fix": "none", "gap_id": ""})

    elif intent == "handoff":
        intent = "handoff"
        for i, g in enumerate(gaps[:3]):
            sug = suggestions[i] if i < len(suggestions) else g.get("detail", "")
            diagnosis.append(_gap_to_diagnosis(g, sug))
        if gaps:
            draft_revision = _build_revision_from_gap(gaps[0], focus_paths, section_map, intent="handoff")
            confidence = 0.75
            apply_mode = "auto"
        else:
            confidence = 0.9
            apply_mode = "auto"

    elif intent == "complaint":
        if not focus_paths and hits:
            focus_paths = [hits[0]["path"]]
        if re.search(r"event\s*3|thử nghiệm", user_message, re.I):
            for h in index:
                if "Thử" in h.get("label_vn", ""):
                    focus_paths = [h["path"]]
                    break
        if re.search(r"nhân vật|character|§1", user_message, re.I):
            focus_paths = ["layers.characters[0]"]
        top_gap: dict[str, Any] = {"id": "user_complaint", "detail": user_message}
        if gaps:
            if re.search(r"event\s*3|thử nghiệm", user_message, re.I):
                event_gaps = [
                    g
                    for g in gaps
                    if "thử" in g.get("id", "").lower()
                    or "synopsis" in g.get("id", "").lower()
                    or "bullets" in g.get("id", "").lower()
                ]
                top_gap = (
                    event_gaps[0]
                    if event_gaps
                    else {"id": "polish_bullets_Thử", "detail": "Event 3 bullet coverage"}
                )
            elif re.search(r"nhân vật|character", user_message, re.I):
                char_gaps = [g for g in gaps if g.get("id", "").startswith(("polish_baseline", "char_"))]
                top_gap = char_gaps[0] if char_gaps else gaps[0]
            else:
                top_gap = gaps[0]
        if focus_paths:
            draft_revision = _build_revision_from_gap(top_gap, focus_paths, section_map, intent="complaint")
            confidence = 0.82
            apply_mode = "auto" if len(focus_paths) == 1 else "confirm"
            if not draft_revision.get("source_excerpt") and hits:
                sid = hits[0].get("section_id", "")
                draft_revision["source_excerpt"] = _excerpt_for_section(section_map, sid)
            diagnosis.append(
                {
                    "issue": top_gap.get("id", "user_complaint"),
                    "evidence": user_message[:200],
                    "suggested_fix": draft_revision.get("instruction", ""),
                    "gap_id": top_gap.get("id", ""),
                }
            )
        else:
            apply_mode = "needs_clarification"
            confidence = 0.3
            clarifying = [
                "Bạn muốn sửa phần nào — Event cụ thể, nhân vật §1, hay mechanics?",
            ]

    else:
        apply_mode = "needs_clarification"
        confidence = 0.4
        clarifying = ["Bạn có thể nói rõ hơn phần nào cần sửa không? (vd. Event 3, nhân vật, check lại)"]

    return {
        "version": 1,
        "user_message": user_message,
        "intent": intent,
        "confidence": confidence,
        "focus_paths": focus_paths,
        "diagnosis": diagnosis,
        "draft_revision": draft_revision,
        "apply_mode": apply_mode,
        "clarifying_questions": clarifying,
    }


def interpret_feedback(
    user_message: str,
    spec: dict[str, Any],
    section_map: list[dict[str, Any]],
    *,
    self_check_report: dict[str, Any] | None = None,
    chat_context: str | None = None,
    client: LMStudioClient | None = None,
    fixture_path: Any = None,
    fidelity_path: Any = None,
) -> dict[str, Any]:
    if self_check_report is None and fixture_path and fidelity_path:
        self_check_report = run_self_check(spec, fixture_path, fidelity_path)

    rules_result = interpret_rules(
        user_message,
        spec,
        section_map,
        self_check_report=self_check_report,
    )

    if client is None:
        return rules_result

    index = build_spec_index(spec, section_map)
    hits = search_index(user_message, index, top_k=5)
    gaps = (self_check_report or {}).get("gaps") or []
    paths = rules_result.get("focus_paths") or [h["path"] for h in hits[:2]]
    spec_slice = spec_slice_for_paths(spec, paths)

    user_prompt = interpret_user_prompt(
        user_message,
        spec_slice,
        hits,
        gaps,
        chat_context=chat_context,
    )
    content = ""
    try:
        content = client.chat(step="interpret", system=INTERPRET_SYSTEM, user=user_prompt, temperature=0.1)
        parsed = extract_json_object(content)
        parsed.setdefault("version", 1)
        if not parsed.get("draft_revision") and rules_result.get("draft_revision"):
            parsed["draft_revision"] = rules_result["draft_revision"]
        return parsed
    except (json.JSONDecodeError, ValueError) as e:
        repair = client.chat(
            step="interpret_repair",
            system="Output only valid JSON.",
            user=repair_user_prompt(str(e), content),
            temperature=0.1,
        )
        try:
            return extract_json_object(repair)
        except (json.JSONDecodeError, ValueError):
            return rules_result
