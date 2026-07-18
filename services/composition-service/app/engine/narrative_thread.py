"""narrative_thread S2 — the OPEN-detection producer (FD-1).

After an auto-generate commit, a best-effort, config-gated LLM pass over the
generated prose detects NEW opened promises/foreshadows/MICE-opens and which of
the project's currently-open threads this scene PAYS, then writes them to the
narrative_thread ledger (open_thread / update_status). This gives the ledger a
real WRITER tied to generation — it was inert (zero callers) since cy14.

Degrade-safe (F1, like canon_reflect): ANY LLM/parse failure is a no-op — it
NEVER fails the generate. The ledger is ADVISORY (spec D4). S3 re-injects
`list_open` into the pack; S4 adds the arc-end unpaid-debt check + eval. This
slice only WRITES the ledger.

Mirrors `canon_check.judge_canon`'s LLM-call shape — including
`reasoning_effort="none"` + `chat_template_kwargs.thinking=False` so a reasoning
model doesn't burn the budget on <think> and emit empty (FD-4 lesson).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.db.repositories.narrative_thread import NarrativeThreadRepo

logger = logging.getLogger(__name__)

_KINDS = {"promise", "foreshadow", "question", "mice_thread"}
# review-impl LOW#3 — bound the open-thread set fed to the detector (prompt
# context + the dedup/pay-validation set). list_open is priority-ordered, so a
# project with many open threads considers the top-N this pass; lower-priority
# old threads beyond the cap aren't paid/deduped here (acceptable for an advisory
# minimal — S3 re-injection owns the real budget/compress).
_OPEN_CONTEXT_CAP = 50


@dataclass
class ThreadUpdateResult:
    """Counts + a status so the caller can log/surface without re-querying."""
    opened: int = 0
    paid: int = 0
    status: str = "ok"  # ok | degraded | empty


def _fold(text: str) -> str:
    """Dedup key: collapse whitespace + lowercase a prefix (mirror the packer/
    SDK `_excerpt_key`) so a re-generated scene doesn't double-open a promise."""
    return re.sub(r"\s+", " ", (text or "")).strip().lower()[:160]


def _build_messages(scene_text: str, open_threads, source_language: str) -> tuple[str, str]:
    """(system, user). Abstract + multilingual-safe (no English-only example
    phrases — they bias a CJK/VN model; the lesson). The model is GIVEN the open
    threads so it can mark pays AND avoid re-opening them."""
    lang = "" if source_language in ("", "auto") else (
        f" Write each `summary` in the language with code '{source_language}'."
    )
    system = (
        "You track narrative promises in a story. A PROMISE is anything the text "
        "plants that the reader will expect to pay off later: a foreshadowing, an "
        "unanswered question, a stated intention/goal, a Chekhov's-gun object, or "
        "a thread opened (milieu/inquiry/character/event). Read the PASSAGE and: "
        "(1) list NEW promises it OPENS that are not already in OPEN_THREADS; "
        "(2) list the ids of OPEN_THREADS this passage PAYS OFF or resolves. "
        "Only include a promise the text actually plants — do NOT invent. Most "
        "passages open 0-2. Return ONLY a JSON object "
        '{"opened":[{"kind":"promise|foreshadow|question|mice_thread","summary":str}],'
        '"paid":[id,...]}.' + lang
    )
    listed = "\n".join(
        f'- id={t.id} kind={t.kind}: {t.summary}' for t in open_threads
    ) or "(none)"
    user = f"OPEN_THREADS:\n{listed}\n\nPASSAGE:\n{scene_text}"
    return system, user


def _parse(content: str) -> tuple[list[dict], list[str]]:
    """Tolerant parse → (opened[], paid_ids[]). Fence-strip + first balanced
    object; filter malformed entries (don't reject the batch — the lesson).
    Empty on hard failure."""
    if not content:
        return [], []
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text).rstrip("`").strip()
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e <= s:
        return [], []
    try:
        obj = json.loads(text[s:e + 1])
    except (ValueError, TypeError):
        return [], []
    if not isinstance(obj, dict):
        return [], []
    opened: list[dict] = []
    for it in obj.get("opened") or []:
        if not isinstance(it, dict):
            continue
        kind = it.get("kind")
        summary = it.get("summary")
        if kind in _KINDS and isinstance(summary, str) and summary.strip():
            opened.append({"kind": kind, "summary": summary.strip(),
                           "trigger": it.get("trigger") if isinstance(it.get("trigger"), str) else ""})
    paid = [str(x) for x in (obj.get("paid") or []) if x is not None]
    return opened, paid


async def detect_and_update_threads(
    llm,
    repo: NarrativeThreadRepo,
    *,
    user_id: UUID,
    project_id: UUID,
    scene_text: str,
    opened_at_node: UUID | None,
    drafter_source: str,
    drafter_ref: str,
    source_language: str = "auto",
    max_open: int = 5,
    max_tokens: int = 1024,
    trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> ThreadUpdateResult:
    """Detect & write narrative-thread updates for one generated passage.

    Best-effort: returns a `degraded` result (no writes) on empty prose or any
    LLM/parse failure — NEVER raises into the generate path (F1)."""
    if not scene_text or not scene_text.strip():
        return ThreadUpdateResult(status="empty")

    open_threads = await repo.list_open(project_id, limit=_OPEN_CONTEXT_CAP)
    open_ids = {str(t.id) for t in open_threads}
    # review-impl LOW#2 (accepted): the fold-dedup is best-effort against THIS
    # snapshot — two scenes generating concurrently for the same project could
    # both open a same-fold promise (TOCTOU; no unique constraint / advisory
    # lock). Advisory + low-harm + gated-off-by-default; a (project,fold) guard
    # or lock is S3/S4 hardening, not built here.
    open_folds = {_fold(t.summary) for t in open_threads}

    system, user = _build_messages(scene_text, open_threads, source_language)
    try:
        job = await llm.submit_and_wait(
            user_id=str(user_id), operation="chat",
            model_source=drafter_source, model_ref=drafter_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"}, "temperature": 0.0,
                "max_tokens": max_tokens, "reasoning_effort": "none",
                # FD-4 lesson: disable thinking so a reasoning model doesn't burn
                # the budget on <think> and emit empty.
                "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
            },
            job_meta={"usage_purpose": "narrative_thread", "extractor": "narrative_thread_detect"}, trace_id=trace_id,
            cancel_check=cancel_check,
        )
    except LLMError as exc:
        logger.warning("narrative_thread detect degraded (LLM error): %s", exc)
        return ThreadUpdateResult(status="degraded")
    if getattr(job, "status", None) != "completed":
        logger.info("narrative_thread detect status=%s → no-op", getattr(job, "status", None))
        return ThreadUpdateResult(status="degraded")

    opened_items, paid_ids = _parse(extract_judge_content(job.result))

    # Pay first: only ids the model was actually GIVEN (guard against invented ids).
    paid = 0
    for tid in paid_ids:
        if tid not in open_ids:
            continue
        try:
            updated = await repo.update_status(
                project_id, UUID(tid), status="paid", payoff_node=opened_at_node,
            )
        except Exception:  # noqa: BLE001 — best-effort per-thread (incl bad UUID)
            continue
        if updated is not None:
            paid += 1

    # Open new threads: dedup by summary fold (vs existing open + within this batch),
    # bounded by max_open so a verbose model can't flood the ledger.
    opened = 0
    for it in opened_items:
        if opened >= max_open:
            break
        fold = _fold(it["summary"])
        if not fold or fold in open_folds:
            continue
        try:
            await repo.open_thread(
                project_id, created_by=user_id, kind=it["kind"], summary=it["summary"],
                opened_at_node=opened_at_node, trigger=it.get("trigger", "") or "",
            )
        except Exception:  # noqa: BLE001 — best-effort per-thread
            logger.warning("narrative_thread open_thread failed (advisory)", exc_info=True)
            continue
        open_folds.add(fold)
        opened += 1

    if opened or paid:
        logger.info(
            "narrative_thread: opened=%d paid=%d project=%s", opened, paid, project_id,
        )
    return ThreadUpdateResult(opened=opened, paid=paid, status="ok")
