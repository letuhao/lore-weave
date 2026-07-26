"""Planning pipeline · Stage 1 — `select_arc_motifs` (the theme/motif step).

The committed plan had `motif_coverage = {}` — the one-shot decompose never *selects*
the themes to weave, even though the motif library + `MotifRetriever` exist. This is
the discrete arc-level selection step: pull the in-genre motif catalog, then have the
LLM pick the few that fit THIS premise/arc — each with a rationale + an arc role —
for a human checkpoint, and to feed the downstream scene decompose as thematic guidance.

REUSE: candidates come from `MotifRetriever.retrieve` with NO beat/query (beat_role=
tension=prev_effects=None) → its degrade path returns the full in-genre pool ranked by
genre+tension with NO min-score floor (the floor only applies to the cosine path). So
the LLM sees the whole catalog and does the semantic pick — no embedding tuning here.

Degrade-safe: empty candidates or any LLM/parse failure → [] (the caller proceeds
motif-less, exactly today's behavior).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient

logger = logging.getLogger(__name__)

_NO_THINK = {
    "reasoning_effort": "none",
    "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
}


@dataclass
class SelectedArcMotif:
    code: str
    name: str
    summary: str
    why: str = ""        # the LLM's rationale for weaving this motif into THIS arc
    arc_role: str = ""   # how it threads (e.g. "central spine", "recurring foil", "climax payoff")


def build_select_motifs_messages(
    premise: str, candidates: list[dict[str, str]], max_select: int,
    source_language: str = "auto",
) -> tuple[str, str]:
    """(system, user). `candidates` = [{code, name, summary}] from the library; the model
    picks BY CODE (so we can map back) — never invents a code."""
    lang = "" if source_language in ("", "auto") else (
        f" Write 'why' and 'arc_role' in the language with code '{source_language}'."
    )
    system = (
        "You are a story architect choosing the THEMATIC MOTIFS to weave through ONE arc. "
        "From the CANDIDATE MOTIFS (a library catalog), select the few that genuinely fit "
        f"this premise — at most {max_select}, fewer if only a few fit; do NOT force a weak "
        "match. For EACH chosen motif return a JSON object with its EXACT `code` from the "
        'catalog (never invent one), a `why` (one line: why it fits this arc), and an '
        '`arc_role` (how it threads — e.g. central spine / recurring / foil / climax payoff). '
        'Return ONLY a JSON array [{"code":...,"why":...,"arc_role":...}]. No prose around it.'
        + lang
    )
    catalog = "\n".join(
        f"- {c['code']}: {c['name']} — {c.get('summary', '')}" for c in candidates
    )
    user = f"PREMISE:\n{premise}\n\nCANDIDATE MOTIFS:\n{catalog}"
    return system, user


def parse_selected_motifs(
    content: str, by_code: dict[str, dict[str, str]],
) -> list[SelectedArcMotif]:
    """Map the model's chosen codes back onto the catalog (drop an unknown/invented code,
    dedup, never raise). `by_code` = {code: {code, name, summary}}."""
    if not content:
        return []
    m = re.search(r"\[.*\]", content, re.DOTALL)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return []
    out: list[SelectedArcMotif] = []
    seen: set[str] = set()
    for row in arr if isinstance(arr, list) else []:
        if not isinstance(row, dict):
            continue
        code = row.get("code")
        if not isinstance(code, str) or code not in by_code or code in seen:
            continue  # unknown/invented/duplicate code → drop (never invent a motif)
        seen.add(code)
        cat = by_code[code]
        out.append(SelectedArcMotif(
            code=code, name=cat.get("name", ""), summary=cat.get("summary", ""),
            why=str(row.get("why", "")).strip(),
            arc_role=str(row.get("arc_role", "")).strip(),
        ))
    return out


async def select_arc_motifs(
    llm: LLMClient, retriever: Any, *, user_id: str, book_id: UUID, project_id: UUID,
    premise: str, genre_tags: list[str], source_language: str = "auto",
    model_source: str, model_ref: str, max_select: int = 4, candidate_limit: int = 15,
    max_tokens: int = 1200, trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> list[SelectedArcMotif]:
    """Pick the arc's thematic motifs from the in-genre library. Returns [] when there are
    no candidates or on any LLM/parse failure (degrade-safe — the caller proceeds motif-less)."""
    # Arc-level retrieve: no beat / tension / query → the degrade path returns the full
    # in-genre pool (no min-score floor), which is exactly the catalog the LLM should pick from.
    cands = await retriever.retrieve(
        UUID(str(user_id)), book_id=book_id, project_id=project_id,
        genre_tags=genre_tags, language=source_language,
        beat_role=None, tension=None, prev_effects=None, limit=candidate_limit,
    )
    if not cands:
        logger.info("select_arc_motifs: no in-genre candidates → motif-less plan")
        return []
    catalog = [{"code": c.motif.code, "name": c.motif.name, "summary": c.motif.summary}
               for c in cands]
    by_code = {c["code"]: c for c in catalog}

    system, user = build_select_motifs_messages(premise, catalog, max_select, source_language)
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"}, "temperature": 0.3,
                "max_tokens": max_tokens, **_NO_THINK,
            },
            job_meta={"usage_purpose": "prose_plan", "extractor": "select_motifs"}, trace_id=trace_id,
            cancel_check=cancel_check,
        )
    except LLMError as exc:
        logger.warning("select_arc_motifs LLM error: %s", exc)
        return []
    if job.status != "completed":
        logger.info("select_arc_motifs status=%s → degraded", job.status)
        return []
    return parse_selected_motifs(extract_judge_content(job.result), by_code)
