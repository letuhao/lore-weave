"""LLM-based propose: analyze → materialize → NovelSystemSpec."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.engine.plan_forge.existing_state import (
    ExistingState,
    merge_existing_into_spec,
    render_existing_state_prompt,
)
from app.engine.plan_forge.json_extract import extract_json_object
from app.engine.plan_forge.links import build_links_from_events, merge_links, normalize_planner_notes
from app.engine.plan_forge.normalize import post_normalize_spec
from app.engine.plan_forge.llm_client import LMStudioClient, default_llm_client
from app.engine.plan_forge.prompts import (
    ANALYZE_SYSTEM,
    MATERIALIZE_SYSTEM,
    analyze_user_prompt,
    materialize_user_prompt,
    repair_user_prompt,
)


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_var_deltas(events: list[dict[str, Any]]) -> None:
    for ev in events:
        for d in ev.get("var_deltas", []):
            d["coupled_to_realm"] = False


def _normalize_synopsis(events: list[dict[str, Any]]) -> None:
    """The materialize prompt asks for a string but doesn't forbid a bullet
    array — observed live (D-PLANFORGE-PA-REALM-FALSE-POSITIVE audit) the
    model sometimes emits `synopsis` as a list of bullet strings instead of
    one joined string, which crashes `validate.run_rules`'s `.lower()` call.
    Coerce to the canonical string shape, same spirit as
    `links.normalize_planner_notes`."""
    for ev in events:
        syn = ev.get("synopsis")
        if isinstance(syn, list):
            ev["synopsis"] = " ".join(str(s).strip() for s in syn if str(s).strip())
        elif syn is None:
            ev["synopsis"] = ""


def _pad_traits_from_analyze(spec: dict[str, Any], analyze: dict[str, Any] | None) -> None:
    if not analyze:
        return
    layers = spec.setdefault("layers", {})
    chars = layers.setdefault("characters", [])
    if not chars:
        chars.append({"id": "char_main", "name": "Nữ chính", "role": "protagonist", "traits": []})
    char = chars[0]
    traits = list(char.get("traits") or [])
    anchors = list(analyze.get("consistency_anchors") or [])
    for a in anchors:
        if a and a not in traits and len(traits) < 5:
            traits.append(a)
    char["traits"] = traits[:5] if len(traits) >= 5 else traits
    if not char.get("baseline_notes") and analyze.get("document_summary"):
        char["baseline_notes"] = analyze["document_summary"]


def normalize_spec(
    spec: dict[str, Any],
    source_checksum: str,
    *,
    analyze: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec.setdefault("version", 1)
    meta = spec.setdefault("meta", {})
    meta.setdefault("title", "STORY PLAN")
    meta.setdefault("version_label", "v1.0")
    meta["source_checksum"] = source_checksum
    charter = spec.setdefault("charter", {})
    charter.setdefault("consistency_anchors", [])
    charter.setdefault("forbids", [])
    charter.setdefault("style_constraints", [])
    layers = spec.setdefault("layers", {})
    layers.setdefault("characters", [])
    layers.setdefault("mechanics", [])
    for i, m in enumerate(layers["mechanics"]):
        m.setdefault("id", f"mechanic_{i + 1}")
    layers.setdefault("variables", [])
    _pad_traits_from_analyze(spec, analyze)
    spec.setdefault("arcs", [])
    spec.setdefault("events", [])
    normalize_planner_notes(spec["events"])
    _normalize_var_deltas(spec["events"])
    _normalize_synopsis(spec["events"])
    auto_links = build_links_from_events(spec["events"])
    spec["links"] = merge_links(spec.get("links", []), auto_links)
    return post_normalize_spec(spec)


def _parse_with_repair(client: LMStudioClient, step: str, system: str, user: str, repair_step: str) -> dict[str, Any]:
    content = client.chat(step=step, system=system, user=user)
    try:
        return extract_json_object(content)
    except (json.JSONDecodeError, ValueError) as e:
        repair_content = client.chat(
            step=repair_step,
            system="Output only valid JSON. No markdown.",
            user=repair_user_prompt(str(e), content),
            max_tokens=12000,
        )
        return extract_json_object(repair_content)


def analyze_document(
    raw_path: Path,
    *,
    client: LMStudioClient | None = None,
    io_dir: Path | None = None,
    existing: ExistingState | None = None,
) -> tuple[dict[str, Any], str]:
    """Step 1 only: analyze markdown → PlanAnalyze. Returns (analyze, source_checksum).

    PROPOSE-BLIND: when `existing` is supplied the prompt gains an EXISTING STATE section so the
    analysis references (not re-invents) the book's arcs/cast. Empty/None ⇒ byte-identical to blind."""
    text = raw_path.read_text(encoding="utf-8")
    checksum = _checksum(text)
    lm = client if client is not None else default_llm_client(io_dir=io_dir)
    block = render_existing_state_prompt(existing) if existing is not None else ""
    analyze = _parse_with_repair(
        lm,
        "analyze",
        ANALYZE_SYSTEM,
        analyze_user_prompt(text, block),
        "analyze_repair",
    )
    analyze.setdefault("version", 1)
    return analyze, checksum


def materialize_from_analyze(
    analyze: dict[str, Any],
    source_checksum: str,
    *,
    client: LMStudioClient | None = None,
    io_dir: Path | None = None,
    existing: ExistingState | None = None,
) -> dict[str, Any]:
    """Step 2 only: PlanAnalyze → NovelSystemSpec.

    PROPOSE-BLIND: the EXISTING STATE section guides the LLM (prompt), and `merge_existing_into_spec`
    is applied as a DETERMINISTIC backstop after normalize — so even if the model imperfectly follows
    the CONTINUITY rule, an existing arc is annotated and an existing character carries its entity id."""
    lm = client if client is not None else default_llm_client(io_dir=io_dir)
    analyze_json = json.dumps(analyze, ensure_ascii=False, indent=2)
    block = render_existing_state_prompt(existing) if existing is not None else ""
    spec = _parse_with_repair(
        lm,
        "materialize",
        MATERIALIZE_SYSTEM,
        materialize_user_prompt(analyze_json, source_checksum, block),
        "materialize_repair",
    )
    spec = normalize_spec(spec, source_checksum, analyze=analyze)
    if analyze.get("open_questions") and not spec.get("meta", {}).get("open_questions"):
        spec["meta"]["open_questions"] = analyze["open_questions"]
    if existing is not None:
        spec = merge_existing_into_spec(spec, existing)
    return spec


def propose_spec_llm(
    raw_path: Path,
    *,
    client: LMStudioClient | None = None,
    io_dir: Path | None = None,
    existing: ExistingState | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run 2-step LLM propose. Returns (novel_system_spec, plan_analyze).

    PROPOSE-BLIND: `existing` threads through both steps (prompt grounding + deterministic merge)."""
    analyze, checksum = analyze_document(raw_path, client=client, io_dir=io_dir, existing=existing)
    spec = materialize_from_analyze(analyze, checksum, client=client, io_dir=io_dir, existing=existing)
    return spec, analyze
