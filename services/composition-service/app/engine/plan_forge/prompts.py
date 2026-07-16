"""Prompt templates for PlanForge LLM propose."""

from __future__ import annotations

import json

ANALYZE_SYSTEM = """You are a novel system architect for LoreWeave — a platform to craft novels with typed specs, planner state machines, and traceability.

Read the user's planning document (natural language, may be Vietnamese). Extract structure into JSON only — no markdown, no prose outside JSON.

Output a single JSON object matching PlanAnalyze v1 with these keys:
- version: 1
- document_summary: one paragraph
- consistency_anchors: string[] (character baseline traits readers must track — use Vietnamese labels from §1.3)
- variables: [{code, name, range, transition_rules[], not_coupled_to[]}] — must include PA, HA, CD, THR if present
- mechanics: [{name, rules[], planner_secrets[]}] — capture §2–§3 bullets faithfully
- arcs: [{id, title, theme, arc_kind, summary}] — arc_kind one of setup|discovery|power|transition|other
- events: [{id, arc_id, title, synopsis, goal, planner_notes[], var_deltas[], source_excerpt?, source_refs?}]
- forbids: string[] (things that must never happen in prose)
- style_constraints: string[]
- open_questions: string[] (unresolved items — do NOT invent answers)

Fidelity requirements (phần đầu):
- ARC COVERAGE (REQUIRED — highest priority): EVERY arc you declare in `arcs` MUST have >= 1 event whose `arc_id` is that arc's id. Distribute events across ALL arcs by their scope in the source; never concentrate all events in a single arc. An arc with no events cannot be compiled — leaving one empty is a generation FAILURE, and the named-arc rules below never excuse it.
- List ALL 5 core traits from §1.3 in consistency_anchors (VN): Thực dụng, Bình dị, Tự giác giới hạn, Giữ lý trí trong khủng hoảng, Hài hước khô
- Arc 2 MUST have exactly 7 events with Vietnamese titles from source (Nhập Môn through Quyết Định Tiếp Tục)
- Each arc_2 event: synopsis >= 2 sentences from source bullets; goal from **Goal:** line; source_excerpt with key bullets
- Mundane-detail anchors from §1.2/§1.3 (mì, mùi, cửa sổ) should appear in anchors or event notes

Critical semantics:
- PA/HA/CD/THR change by EXPERIENCE not cultivation realm
- Arc 2 in this story is DISCOVERY not power fantasy if the doc says so
- THR is long-game; do not explain past-life in early arcs
- Preserve planner notes verbatim where found
- Keep Vietnamese for event titles and user-facing anchor text"""

MATERIALIZE_SYSTEM = """You are a novel system architect. Convert PlanAnalyze into NovelSystemSpec v1 — JSON only.

Required top-level keys: version, meta, charter, layers, arcs, events, links

Structure:
- version: 1
- meta: {title, version_label, source_checksum, open_questions}
- charter: {consistency_anchors, forbids, style_constraints}
- layers: {characters: [{id, name, role, traits, baseline_notes}], mechanics: [{id, name, rules, planner_secrets}], variables: [...]}
- arcs: [{id, title, theme, arc_kind, summary, exit_state?}]
- events: [{id, arc_id, title, synopsis, goal, planner_notes, var_deltas: [{variable, delta, reason, coupled_to_realm: false}]}]
- links: [{from, to, kind, note}] — kind: event_constrains_variable|event_preserves_anchor|event_foreshadows|arc_depends_on_mechanic|variable_governs_tier

Fidelity requirements:
- ARC COVERAGE (REQUIRED — highest priority, governs the arc-specific rules below): EVERY arc in `arcs` MUST have >= 1 event whose `arc_id` equals that arc's own id. Distribute events across ALL arcs in proportion to each arc's scope in the source — an arc that spans several chapters gets several events. NEVER put every event in one arc. An arc with zero events CANNOT be compiled and is a generation FAILURE — the arc-specific fixture rules below apply to their named arc but do NOT excuse leaving any other arc empty.
- layers.characters[0].traits: exactly 5 strings in Vietnamese from §1.3
- baseline_notes: summarize §1.1–§1.3 in VIETNAMESE (>=200 chars, >=35% VN diacritics); include mundane details (mì, mùi, cửa sổ)
- character name: use "Nữ chính" or source name — never "Female Protagonist" or "TBD"
- mechanics: at least 3 entries with >=2 rules each from §2–§3; >=50% rules in Vietnamese; planner_secrets for THR/tiền kiếp
- arc_2 events: keep Vietnamese titles; synopsis >=80 chars as condensed bullet list from source (not meta summaries)
- Arc 2 MUST include exactly these 7 events (titles in Vietnamese): Nhập Môn, Biến Hóa Đầu Tiên, Thử Nghiệm, Dị Thường Đầu Tiên, Tiểu Thành, Tác Dụng Phụ Đầu Tiên, Quyết Định Tiếp Tục
- Event 3 Thử Nghiệm: must mention tốc độ, linh thạch, âm dương, logic nhân vật
- Do NOT translate event titles to English

Rules:
- coupled_to_realm must always be false for var_deltas
- arc_2 arc_kind must be "discovery" if analyze says discovery/khám phá
- Include links from events to variables and anchors where planner notes imply constraints
- Do not drop open_questions from analyze"""

REFINE_ANALYZE_SYSTEM = """You are a novel system architect. Apply a surgical revision to PlanAnalyze JSON only.

Rules:
- Output the FULL updated PlanAnalyze JSON — no markdown, no prose outside JSON
- Apply ONLY the revision instruction; do not refactor unrelated fields
- Do NOT modify anything listed in frozen_paths
- Honor every item in constraint_ledger
- Do NOT invent answers to open_questions
- Preserve PA/HA/CD/THR semantics: experience-driven, not cultivation realm
- intent=completeness: fill gaps vs source_excerpt first; do not drop existing correct fields
- Keep Vietnamese event titles and trait labels"""

REFINE_SPEC_SYSTEM = """You are a novel system architect. Apply a surgical revision to NovelSystemSpec JSON only.

Rules:
- Output the FULL updated NovelSystemSpec v1 JSON — no markdown
- Apply ONLY the revision instruction
- Do NOT modify frozen_paths (variable codes, arc_2 arc_kind, charter.forbids unless scope allows)
- Honor constraint_ledger
- coupled_to_realm must stay false on all var_deltas
- Keep Vietnamese event titles when source uses Vietnamese
- intent=completeness: expand traits, baseline_notes, mechanics rules, event synopses per source_excerpt
- Do not shorten synopses below 80 chars when expanding
- Polish: baseline_notes must be Vietnamese; expand Event 3 with source bullets"""

INTERPRET_SYSTEM = """You are a PlanForge feedback interpreter. Convert vague user feedback into structured JSON only.

Output FeedbackInterpretation v1:
{
  "version": 1,
  "user_message": "...",
  "intent": "complaint|recheck|handoff|clarify",
  "confidence": 0.0-1.0,
  "focus_paths": ["events[id]", "layers.characters[0]", ...],
  "diagnosis": [{"issue": "...", "evidence": "...", "suggested_fix": "...", "gap_id": "..."}],
  "draft_revision": { PlanRevisionRequest with target spec, instruction, scope, frozen_paths, source_excerpt },
  "apply_mode": "confirm|auto|needs_clarification",
  "clarifying_questions": []
}

Rules:
- recheck ("check lại", "xem lại"): use provided gaps as diagnosis; apply_mode confirm unless single gap
- complaint ("sai chỗ này"): use focus_paths from index hits; draft surgical revision with VN source excerpt
- handoff ("làm đi", "sửa hết"): apply_mode auto; prioritize character then events then mechanics
- confidence < 0.6 → confirm; >= 0.8 with one focus_path → auto eligible
- frozen_paths: always include variables, arcs; charter.forbids unless scope allows
- instruction in Vietnamese when user writes Vietnamese"""

ELABORATE_SYSTEM = """You are a novel system architect. Elaborate NovelSystemSpec v1.1 character fields only.

Output JSON with key character_elaboration:
{
  "character_elaboration": {
    "behavioral_rules": string[] (VN, from §1.3–§1.6 recognition checklist),
    "relationship_seeds": string[] (VN, from §1.4 beauty relationship),
    "recognition_tiers": string[] (VN, tier 0–3 drift signs from §1.6)
  }
}

Rules:
- Do NOT modify variables, charter.forbids, arcs, events, or event order
- Vietnamese text for all new strings
- Base content only on provided section excerpts"""


def analyze_user_prompt(markdown: str) -> str:
    return f"""Analyze this planning document and output PlanAnalyze JSON only.

<plan_document>
{markdown}
</plan_document>"""


def materialize_user_prompt(analyze_json: str, source_checksum: str) -> str:
    return f"""Materialize this PlanAnalyze into NovelSystemSpec v1 JSON only.

source_checksum for meta: {source_checksum}

<plan_analyze>
{analyze_json}
</plan_analyze>"""


def refine_user_prompt(current_json: str, revision: dict) -> str:
    rev_json = json.dumps(revision, ensure_ascii=False, indent=2)
    excerpt = revision.get("source_excerpt") or ""
    excerpt_block = f"\n<source_excerpt>\n{excerpt}\n</source_excerpt>\n" if excerpt else ""
    intent = revision.get("intent", "")
    intent_line = f"\nRevision intent: {intent}\n" if intent else ""
    return f"""Apply this revision to the current artifact. Output full JSON only.
{intent_line}
<plan_revision>
{rev_json}
</plan_revision>
{excerpt_block}
<current_artifact>
{current_json}
</current_artifact>"""


def elaborate_user_prompt(spec_json: str, section_excerpts: dict[str, str], scope: list[str]) -> str:
    excerpts_json = json.dumps(section_excerpts, ensure_ascii=False, indent=2)
    return f"""Elaborate character fields for scope: {', '.join(scope)}.

<section_excerpts>
{excerpts_json}
</section_excerpts>

<novel_system_spec>
{spec_json}
</novel_system_spec>"""


def interpret_user_prompt(
    user_message: str,
    spec_slice: str,
    index_hits: list[dict],
    gaps: list[dict],
    chat_context: str | None = None,
) -> str:
    hits_json = json.dumps(index_hits[:5], ensure_ascii=False, indent=2)
    gaps_json = json.dumps(gaps[:10], ensure_ascii=False, indent=2)
    ctx = f"\n<chat_context>\n{chat_context}\n</chat_context>\n" if chat_context else ""
    return f"""Interpret this vague user feedback for PlanForge revision.
{ctx}
<user_message>
{user_message}
</user_message>

<spec_index_hits>
{hits_json}
</spec_index_hits>

<self_check_gaps>
{gaps_json}
</self_check_gaps>

<spec_slice>
{spec_slice}
</spec_slice>"""


def repair_user_prompt(error: str, invalid_json: str) -> str:
    truncated = invalid_json[:6000]
    return f"""The previous JSON was invalid. Fix it and output ONLY valid JSON.

Parse error: {error}

<invalid_json>
{truncated}
</invalid_json>"""
