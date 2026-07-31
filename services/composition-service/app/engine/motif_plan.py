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

from app.packer.sanitize import neutralize

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from loreweave_llm import no_thinking_fields
from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient

logger = logging.getLogger(__name__)


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
    # D-INJECTION-COVERAGE (2026-07-31): `premise` is the author's own text, and the motif
    # names/summaries are authored or MINED FROM IMPORTED SOURCE MATERIAL — both arbitrary,
    # both concatenated straight into a prompt. Flagged by `injection-coverage-lint` all
    # along; the lint had never run in CI.
    catalog = "\n".join(
        f"- {c['code']}: {neutralize(c['name'])} — {neutralize(c.get('summary', ''))}"
        for c in candidates
    )
    user = f"PREMISE:\n{neutralize(premise)}\n\nCANDIDATE MOTIFS:\n{catalog}"
    return system, user


def parse_selected_motifs(
    content: str, by_code: dict[str, dict[str, str]],
    *, dropped: list[str] | None = None,
) -> list[SelectedArcMotif]:
    """Map the model's chosen codes back onto the catalog (drop an unknown/invented code,
    dedup, never raise). `by_code` = {code: {code, name, summary}}.

    `dropped` — an out-param the caller passes to LEARN which codes were discarded. The drop was
    silent, and silence here is a lie: 30 candidates went to the model, it answered with codes that
    were not in the catalog, every one was dropped, and the pass then reported "no motif matched
    this arc — the library had no candidate for its language/genre". The author reads that as an
    empty library. It was a selection failure wearing a retrieval failure's message.

    Catalog codes are machine-ugly (`3b.faceslap.1784257099`, `bs.bound.1784278101`), so a model
    asked to echo them verbatim really does fumble them — this is the expected failure, not an
    exotic one. Matching is therefore case-insensitive and whitespace-trimmed, which recovers a
    genuine near-miss WITHOUT ever inventing: an unrecognised code is still dropped, just loudly.
    """
    if not content:
        return []
    m = re.search(r"\[.*\]", content, re.DOTALL)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return []
    # Fold once, so a case/whitespace near-miss resolves to the REAL catalog code.
    folded = {c.strip().casefold(): c for c in by_code}
    out: list[SelectedArcMotif] = []
    seen: set[str] = set()
    for row in arr if isinstance(arr, list) else []:
        if not isinstance(row, dict):
            continue
        raw = row.get("code")
        if not isinstance(raw, str) or not raw.strip():
            continue
        code = by_code.get(raw) and raw or folded.get(raw.strip().casefold())
        if code is None:
            # INVENTED — record it so the caller can say so instead of blaming the library.
            if dropped is not None:
                dropped.append(raw.strip()[:80])
            continue
        if code in seen:
            continue
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
    # Arc-level retrieve, SEEDED WITH THE PREMISE.
    #
    # This used to pass no query at all, on the reasoning that "the LLM sees the whole catalog
    # and does the semantic pick". That held when the library was ~44 codes; it stopped being
    # true silently. With no query the degrade path scores every row `0.6*genre + 0.4*tension`,
    # and the real calls supply neither (286 of 292 plan runs carry `genre_tags: []`), so every
    # row tied and the `candidate_limit` was handed out by the tie-break — alphabetically, which
    # meant 15/15 `cultivation.*`. The model then reported, accurately, that the catalog was all
    # cultivation tropes; the catalog was not, the ORDERING was. The premise was sitting right
    # here in the signature the whole time, used only for the prompt.
    #
    # Seeding it makes the library section rank by actual semantic fit to THIS arc across every
    # pack. If the cosine floor (`motif_min_score`) admits nothing — a premise unlike anything
    # in the library — fall back to the unseeded call, so this can only ever ADD reach.
    async def _retrieve(query: str | None) -> list[Any]:
        return await retriever.retrieve(
            UUID(str(user_id)), book_id=book_id, project_id=project_id,
            genre_tags=genre_tags, display_language=source_language,
            beat_role=None, tension=None, prev_effects=None, limit=candidate_limit,
            query=query,
        )

    cands = await _retrieve(premise)
    if not cands:
        cands = await _retrieve(None)
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
                "max_tokens": max_tokens, **no_thinking_fields(),
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
    dropped: list[str] = []
    selected = parse_selected_motifs(extract_judge_content(job.result), by_code, dropped=dropped)
    if dropped:
        # Loud on purpose. This is the difference between "your library is empty" and "the model
        # answered with codes that do not exist", and only one of those is the author's problem.
        logger.warning(
            "select_arc_motifs: %d of %d chosen code(s) were NOT in the catalog of %d and were "
            "dropped — %s", len(dropped), len(dropped) + len(selected), len(catalog), dropped[:5],
        )
    return selected
