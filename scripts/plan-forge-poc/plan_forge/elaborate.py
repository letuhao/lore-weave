"""Elaboration engine — enrich spec after Phase A fidelity gate."""

from __future__ import annotations

import json
from typing import Any

from plan_forge.json_extract import extract_json_object
from plan_forge.llm_client import LMStudioClient
from plan_forge.prompts import ELABORATE_SYSTEM, elaborate_user_prompt, repair_user_prompt
from plan_forge.propose_llm import normalize_spec


def consistency_audit(spec: dict[str, Any]) -> dict[str, Any]:
    """Rule-based cross-checks — heuristic, not LLM judge."""
    critical: list[str] = []
    warnings: list[str] = []

    chars = (spec.get("layers") or {}).get("characters") or []
    char = chars[0] if chars else {}
    traits_blob = " ".join(char.get("traits") or []).lower()
    anchors = " ".join((spec.get("charter") or {}).get("consistency_anchors") or []).lower()
    baseline = traits_blob + " " + anchors

    arc2_events = [e for e in spec.get("events", []) if e.get("arc_id") == "arc_2"]
    for ev in arc2_events:
        syn = (ev.get("synopsis") or "").lower()
        title = ev.get("title") or ev.get("id")
        if "bình dị" in baseline or "mundane" in baseline:
            if any(k in syn for k in ("tối thượng", "supreme power", "power fantasy", "vô địch")):
                if ev.get("id") not in ("arc_2_event_5", "ev_2_5"):
                    warnings.append(f"{title}: synopsis may contradict mundane baseline")
        if any(k in syn for k in ("tiền kiếp", "past life", "mị đế")) and "giải thích" in syn:
            if "arc_2_event_4" not in (ev.get("id") or "") and "ev_2_4" not in (ev.get("id") or ""):
                critical.append(f"{title}: early THR/past-life explanation in synopsis")

    forbids = " ".join((spec.get("charter") or {}).get("forbids") or []).lower()
    if "tiết lộ" in forbids or "explain" in forbids:
        for ev in arc2_events[:4]:
            syn = (ev.get("synopsis") or "").lower()
            if "thr" in syn and "giải thích" in syn:
                critical.append(f"{ev.get('title')}: THR explained too early")

    return {"critical": critical, "warnings": warnings}


def _parse_with_repair(client: LMStudioClient, step: str, system: str, user: str) -> dict[str, Any]:
    content = client.chat(step=step, system=system, user=user, temperature=0.15)
    try:
        return extract_json_object(content)
    except (json.JSONDecodeError, ValueError) as e:
        repair_content = client.chat(
            step=f"{step}_repair",
            system="Output only valid JSON. No markdown.",
            user=repair_user_prompt(str(e), content),
            max_tokens=12000,
            temperature=0.1,
        )
        return extract_json_object(repair_content)


def elaborate_spec(
    spec: dict[str, Any],
    section_excerpts: dict[str, str],
    *,
    client: LMStudioClient,
    source_checksum: str,
    scope: list[str] | None = None,
) -> dict[str, Any]:
    """Add v1.1 fields (behavioral_rules, relationship_seeds, recognition_tiers) without mutating core."""
    scope = scope or ["character_elaboration"]
    payload = elaborate_user_prompt(
        json.dumps(spec, ensure_ascii=False, indent=2),
        section_excerpts,
        scope,
    )
    out = _parse_with_repair(client, "elaborate", ELABORATE_SYSTEM, payload)
    merged = json.loads(json.dumps(spec))
    chars = merged.setdefault("layers", {}).setdefault("characters", [])
    if chars and out.get("character_elaboration"):
        ce = out["character_elaboration"]
        for key in ("behavioral_rules", "relationship_seeds", "recognition_tiers"):
            if key in ce:
                chars[0][key] = ce[key]
    return normalize_spec(merged, source_checksum)


def section_excerpts_for_elaboration(section_map: list[dict[str, Any]]) -> dict[str, str]:
    """§1.4–§1.6 and §6.x writing principles for elaboration."""
    wanted = {"1.4", "1.5", "1.6"}
    out: dict[str, str] = {}
    for s in section_map:
        sid = str(s["section_id"])
        if sid in wanted or sid.startswith("6."):
            out[sid] = s.get("excerpt", "")
    return out
