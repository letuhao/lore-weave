"""Planning pipeline · Stage 5 — `run_plan_self_heal` (judge → fix-scene → apply).

The chapter self-heal (`engine/self_heal.py`) proved the pattern for PROSE:
judge → locate → satellite-edit → splice. This applies the SAME pattern to the PLAN
(the outline), with one simplification — a plan is a list of discrete, INDEX-ADDRESSABLE
scenes, so the judge points at a scene by its (chapter, scene) number and "locate" is a
lookup, not a fuzzy text match. A plan-judge reads the whole outline and flags plan-level
defects (a character present before its introduction, an unused selected motif, a dangling
setup, a tension that fights its beat, a scene that doesn't advance); each flagged scene's
SYNOPSIS is satellite-edited (in isolation + light neighbor context) and written back.

Advisory + degrade-safe: a finding that addresses no real scene, or whose edit fails /
runs away in length, is SKIPPED (the original synopsis is kept). A judge failure returns
the plan unchanged.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient
from app.engine.plan import DecomposeResult

logger = logging.getLogger(__name__)

_NO_THINK = {
    "reasoning_effort": "none",
    "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
}


@dataclass
class PlanFinding:
    chapter: int          # 1-based
    scene: int            # 1-based within the chapter
    type: str = ""
    issue: str = ""
    fix: str = ""
    applied: bool = False
    skip_reason: str | None = None   # not_found | edit_failed | edit_expanded


@dataclass
class PlanHealReport:
    findings: list[PlanFinding] = field(default_factory=list)
    edits_applied: int = 0


def render_outline(result: DecomposeResult) -> str:
    """The outline as judge-readable, index-addressed lines: `CH02 S3 [beat] (tension): synopsis`."""
    lines: list[str] = []
    for ci, cs in enumerate(result.chapters, start=1):
        beat = cs.chapter.beat_role or "-"
        for si, sc in enumerate(cs.scenes, start=1):
            lines.append(f"CH{ci:02d} S{si} [{beat}] (tension {sc.tension}): {sc.synopsis}")
    return "\n".join(lines)


def build_plan_judge_messages(outline: str, source_language: str = "auto") -> tuple[str, str]:
    system = (
        "You are a demanding story editor reviewing a chapter-by-chapter OUTLINE (each line "
        "is one scene, addressed CHxx Sy with its beat + tension). Find PLAN-level defects: a "
        "character acting before they are introduced; a tension that fights its beat (e.g. a "
        "max-tension opening, or a flat climax); a dangling setup (something set up that no "
        "later scene pays off); cross-chapter repetition; a scene that does not advance the "
        "story. For EACH defect return a JSON object addressing the scene by number: "
        '"chapter" (int), "scene" (int), "type", "issue", and "fix" (a concrete one-line fix). '
        'Write issue/fix in the outline\'s language. Choose the 5-8 clearest defects. Return '
        'ONLY a JSON array [{"chapter":int,"scene":int,"type":...,"issue":...,"fix":...}].'
    )
    return system, "OUTLINE:\n\n" + outline


def parse_plan_findings(content: str) -> list[PlanFinding]:
    """Tolerant parse; drops a row without int chapter+scene. Never raises."""
    if not content:
        return []
    m = re.search(r"\[.*\]", content, re.DOTALL)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return []
    out: list[PlanFinding] = []
    for row in arr if isinstance(arr, list) else []:
        if not isinstance(row, dict):
            continue
        ch, sc = row.get("chapter"), row.get("scene")
        if isinstance(ch, bool) or isinstance(sc, bool) or not isinstance(ch, int) or not isinstance(sc, int):
            continue
        out.append(PlanFinding(
            chapter=ch, scene=sc, type=str(row.get("type", "")).strip(),
            issue=str(row.get("issue", "")).strip(), fix=str(row.get("fix", "")).strip(),
        ))
    return out


async def _chat(llm, *, user_id, model_source, model_ref, system, user, max_tokens, purpose,
                trace_id, cancel_check) -> str | None:
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                   "response_format": {"type": "text"}, "temperature": 0.3, "max_tokens": max_tokens, **_NO_THINK},
            job_meta={"usage_purpose": purpose, "extractor": "plan_heal"}, trace_id=trace_id,
            cancel_check=cancel_check)
    except LLMError as exc:
        logger.warning("plan_heal %s LLM error: %s", purpose, exc)
        return None
    if job.status != "completed":
        return None
    c = extract_judge_content(job.result)
    return c if c.strip() else None


def build_fix_scene_messages(
    synopsis: str, issue: str, fix: str, neighbors: str, source_language: str = "auto",
) -> tuple[str, str]:
    lang = "" if source_language in ("", "auto") else (
        f" Write in the language with code '{source_language}'."
    )
    system = (
        "You are revising ONE scene's synopsis in a story outline to fix a specific issue. "
        "Keep it a synopsis (goal · conflict · outcome), the SAME approximate length, and "
        "consistent with the neighboring scenes. Output ONLY the revised synopsis — no "
        "preamble, no quotes, no commentary." + lang
    )
    user = (
        (f"NEIGHBORING SCENES (for continuity, do not rewrite them):\n{neighbors}\n\n" if neighbors else "")
        + f"ISSUE: {issue}\nFIX: {fix}\n\nSCENE SYNOPSIS TO REVISE:\n{synopsis}"
    )
    return system, user


async def run_plan_self_heal(
    llm: LLMClient, result: DecomposeResult, *, user_id: str, model_source: str, model_ref: str,
    source_language: str = "auto", max_edit_expansion: float = 1.6,
    judge_max_tokens: int = 2000, edit_max_tokens: int = 700,
    trace_id: str | None = None, cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> tuple[DecomposeResult, PlanHealReport]:
    """Judge the outline, satellite-edit each flagged scene's synopsis IN PLACE, return the
    healed result + report. Degrade-safe (a judge failure returns the plan unchanged; each
    per-finding failure is skipped)."""
    kw = dict(user_id=user_id, model_source=model_source, model_ref=model_ref,
              trace_id=trace_id, cancel_check=cancel_check)
    sysj, usrj = build_plan_judge_messages(render_outline(result), source_language)
    jc = await _chat(llm, system=sysj, user=usrj, max_tokens=judge_max_tokens,
                     purpose="plan_judge", **kw)
    findings = parse_plan_findings(jc or "")
    report = PlanHealReport(findings=findings)
    if not findings:
        return result, report

    for f in findings:
        ci, si = f.chapter - 1, f.scene - 1
        if not (0 <= ci < len(result.chapters)):
            f.skip_reason = "not_found"
            continue
        scenes = result.chapters[ci].scenes
        if not (0 <= si < len(scenes)):
            f.skip_reason = "not_found"
            continue
        target = scenes[si]
        # light neighbor context: the prior + next scene synopses in the chapter
        neigh = "\n".join(
            f"S{j + 1}: {scenes[j].synopsis}"
            for j in (si - 1, si + 1) if 0 <= j < len(scenes)
        )
        syse, usre = build_fix_scene_messages(target.synopsis, f.issue, f.fix, neigh, source_language)
        new = await _chat(llm, system=syse, user=usre, max_tokens=edit_max_tokens,
                          purpose="plan_fix_scene", **kw)
        if not new:
            f.skip_reason = "edit_failed"
            continue
        new = new.strip()
        if len(new) > max(40, len(target.synopsis)) * max_edit_expansion:
            f.skip_reason = "edit_expanded"
            continue
        target.synopsis = new
        f.applied = True
        report.edits_applied += 1

    return result, report
