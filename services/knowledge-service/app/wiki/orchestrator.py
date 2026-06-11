"""wiki-llm M6 — the batch generation orchestrator.

A fresh, ~150-line entity-loop that ties the M2–M5 building blocks together for
one job (risk #12: BUILD FRESH reusing the GENERIC infra — state_machine, budget,
the LLMClient — NOT a clone of lore-enrichment's gap/proposal-coupled JobRunner).
Per entity:

    gather_entity_context (M2) → generate_article (M3) → verify_article +
    revise_article (M4) → compose_provenance_cites + build_inputs (M4/M5) →
    build_writeback_body → glossary write_wiki_article (M5)

Resilient by construction: a per-entity failure is logged and SKIPPED (the batch
never crashes); ``items_done`` makes a paused/restarted job skip what it already
wrote; the per-article cost estimate is charged against ``max_spend_usd`` and the
job PAUSES (status='paused', reason=budget) when the cap is hit — never silently
overspends. Cost is a configured ESTIMATE per generated article (the LLMClient
meters real tokens through provider-registry; precise per-job metering is a
follow-up — D-WIKI-M6-PRECISE-COST).
"""

from __future__ import annotations

import logging
import random
from decimal import Decimal

from app.clients.book_client import BookClient
from app.clients.book_profile_client import BookProfileClient
from app.clients.embedding_client import EmbeddingClient
from app.clients.glossary_client import GlossaryClient
from app.clients.learning_client import post_wiki_judge
from app.clients.llm_client import LLMClient
from app.clients.reranker_client import RerankerClient
from app.config import settings
from app.extraction.injection_defense import neutralize_injection
from app.db.models import Project
from app.db.repositories.wiki_gen_jobs import WikiGenJob, WikiGenJobsRepo
from app.wiki.context import gather_entity_context
from app.wiki.fingerprint import compute_build_inputs
from app.wiki.generate import generate_article
from app.wiki.mappers import ir_to_plaintext
from app.wiki.revise import revise_article
from app.wiki.cite import compose_provenance_cites
from app.wiki.verify import verify_article
from app.wiki.writeback import build_writeback_body

logger = logging.getLogger(__name__)

__all__ = ["run_wiki_gen_job", "OrchestratorClients"]


class OrchestratorClients:
    """The seam-injected clients the orchestrator drives (so a test passes mocks)."""

    def __init__(
        self, *, glossary: GlossaryClient, book: BookClient,
        embedding: EmbeddingClient, reranker: RerankerClient,
        llm: LLMClient, book_profile: BookProfileClient,
    ) -> None:
        self.glossary = glossary
        self.book = book
        self.embedding = embedding
        self.reranker = reranker
        self.llm = llm
        self.book_profile = book_profile


async def _generate_one(
    *, entity_id: str, job: WikiGenJob, project: Project, profile,
    clients: OrchestratorClients, retrieval_params: dict,
    prompt_version: str, pipeline_version: str,
    exemplars: list[tuple[str, str]] | None = None,
) -> str:
    """Run the full pipeline for ONE entity. Returns an outcome token
    ('written' | 'suggestion' | 'skipped' | 'writeback_failed'). Never raises."""
    context = await gather_entity_context(
        entity_id=entity_id, book_id=job.book_id, user_id=job.user_id, project=project,
        glossary_client=clients.glossary, book_client=clients.book,
        embedding_client=clients.embedding, reranker_client=clients.reranker,
    )
    if context is None:
        return "skipped"

    gen = await generate_article(
        context=context, profile=profile, llm=clients.llm, user_id=str(job.user_id),
        model_source=job.model_source, model_ref=job.model_ref, exemplars=exemplars,
    )
    if gen.status != "ok" or gen.ir is None:
        logger.info("wiki-gen skip entity=%s status=%s", entity_id, gen.status)
        return "skipped"

    verify = await verify_article(gen.ir, context, profile)
    gen, verify = await revise_article(
        gen=gen, verify=verify, context=context, profile=profile, llm=clients.llm,
        user_id=str(job.user_id), model_source=job.model_source, model_ref=job.model_ref,
    )
    if gen.ir is None:
        return "skipped"

    cites = await compose_provenance_cites(gen.ir)
    build_inputs = compute_build_inputs(
        context=context, model_ref=job.model_ref,
        prompt_version=prompt_version, pipeline_version=pipeline_version,
        retrieval_params=retrieval_params,
    )
    body = build_writeback_body(
        context=context, ir=gen.ir, verify=verify, cites=cites, build_inputs=build_inputs,
        model_ref=job.model_ref, user_id=job.user_id, grounding_params=retrieval_params,
        prompt_version=prompt_version, pipeline_version=pipeline_version,
    )
    result = await clients.glossary.write_wiki_article(job.book_id, body=body)
    if result is None:
        return "writeback_failed"
    action = str(result.get("action") or "written")
    await _maybe_judge(
        job=job, context=context, ir=gen.ir, article_id=result.get("article_id"), action=action)
    return action


async def _fetch_exemplars(job: WikiGenJob, clients: OrchestratorClients) -> list[tuple[str, str]]:
    """D-WIKI-M8-FEWSHOT — fetch the book's gold AI→human pairs ONCE per job (gated
    OFF by default). Best-effort: any failure / empty → [] (generation runs exactly as
    before, no exemplars). Each pair is (ai_text, human_text); the glossary endpoint
    has already flattened + truncated the bodies.

    /review-impl F1: exemplar bodies are UNTRUSTED text (an owner edit, or the model's
    own prior draft) and they land in the higher-trust SYSTEM role — so they get the
    SAME tag-don't-delete injection defense (`neutralize_injection`) that M2 applies to
    context sources, closing the asymmetry where sources were sanitized but exemplars
    weren't."""
    if not settings.wiki_fewshot_enabled:
        return []
    try:
        pairs = await clients.glossary.fetch_wiki_gold_pairs(
            job.book_id, limit=settings.wiki_fewshot_max_examples)
        out: list[tuple[str, str]] = []
        for p in pairs:
            ai = neutralize_injection(p.get("ai_text") or "")[0]
            human = neutralize_injection(p.get("human_text") or "")[0]
            if ai and human:
                out.append((ai, human))
        return out
    except Exception:  # noqa: BLE001 — exemplars are an optional enhancement
        logger.warning("wiki few-shot exemplar fetch failed (non-fatal)", exc_info=True)
        return []


def _sampled(rate: float) -> bool:
    """Sampling decision. Deterministic at the bounds (1.0 always / ≤0 never) so the
    auto-judge is testable; random in between."""
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    return random.random() < rate


async def _maybe_judge(*, job: WikiGenJob, context, ir, article_id, action: str) -> None:
    """D-WIKI-M8-EVAL-PLUS Phase 2 — automatic-sampled groundedness judge. With
    probability `wiki_llm_judge_sample_rate`, post the fresh article + its FULL context
    sources to the learning judge endpoint. Gated OFF (flag + rate 0 + no model = no
    call). Best-effort: never blocks or fails generation.

    Only a DIRECT write is judged: when the AI body was clobber-guarded into a
    suggestion (``action='suggestion'`` — the article had human edits), ``gen.ir`` is
    NOT the live article, so scoring it against this article_id would misattribute the
    suggestion's groundedness to the human article."""
    try:
        if action != "written":
            return
        if not (settings.wiki_llm_judge_enabled and settings.wiki_llm_judge_model_ref and article_id):
            return
        if not _sampled(settings.wiki_llm_judge_sample_rate):
            return
        sources = [it.text for it in context.items if it.text]
        await post_wiki_judge(
            article_id=article_id, book_id=job.book_id, user_id=job.user_id,
            article_text=ir_to_plaintext(ir), sources=sources,
            judge_model=settings.wiki_llm_judge_model_ref,
            model_source=settings.wiki_llm_judge_model_source,
        )
    except Exception:  # noqa: BLE001 — the auto-judge is best-effort telemetry
        logger.warning("wiki auto-judge failed (non-fatal)", exc_info=True)


async def run_wiki_gen_job(
    job: WikiGenJob,
    *,
    repo: WikiGenJobsRepo,
    project: Project,
    clients: OrchestratorClients,
    retrieval_params: dict,
    prompt_version: str,
    pipeline_version: str,
    cost_per_article_usd: Decimal,
) -> str:
    """Drive a whole wiki-gen job. Returns the terminal status ('complete' |
    'paused' | 'failed'). Skips entities in ``items_done`` (resume), charges the
    per-article estimate against the cap, and pauses on budget breach."""
    entity_ids = job.entity_ids
    try:
        claimed = await repo.mark_running(job.job_id, items_total=len(entity_ids))
    except Exception as exc:  # noqa: BLE001 — a status write failure shouldn't crash the run
        logger.warning("wiki-gen mark_running failed job=%s: %s", job.job_id, exc)
        claimed = True  # a transient write failure is not a cancel — proceed (skip-done is safe)
    if not claimed:
        # The job is no longer claimable (a concurrent cancel flipped it to
        # 'cancelled', or it already reached a terminal state). Do NOT run — that
        # would resurrect a cancelled job + spend tokens (M7b /review-impl F1).
        logger.info("wiki-gen job=%s not claimable (cancelled/terminal) — skipping", job.job_id)
        return "cancelled"

    done = set(job.items_done)
    spent = job.cost_spent_usd
    cap = job.max_spend_usd
    writeback_failures = 0
    profile = await clients.book_profile.get_profile(job.book_id)
    exemplars = await _fetch_exemplars(job, clients)  # D-WIKI-M8-FEWSHOT (book-level, once)

    for entity_id in entity_ids:
        if entity_id in done:
            continue
        # Budget gate BEFORE the spend: pause (resumable) rather than overspend.
        if cap is not None and spent + cost_per_article_usd > cap:
            await repo.pause(job.job_id, reason="budget")
            logger.info("wiki-gen paused on budget job=%s spent=%s cap=%s",
                        job.job_id, spent, cap)
            return "paused"
        try:
            outcome = await _generate_one(
                entity_id=entity_id, job=job, project=project, profile=profile,
                clients=clients, retrieval_params=retrieval_params,
                prompt_version=prompt_version, pipeline_version=pipeline_version,
                exemplars=exemplars,
            )
        except Exception as exc:  # noqa: BLE001 — one entity must not crash the batch
            logger.warning("wiki-gen entity failed job=%s entity=%s: %s",
                           job.job_id, entity_id, exc)
            continue
        if outcome == "writeback_failed":
            # leave the entity NOT done so a resume retries it; don't charge.
            writeback_failures += 1
            continue
        charge = cost_per_article_usd if outcome in ("written", "suggestion") else Decimal("0")
        spent += charge
        await repo.mark_entity_done(job.job_id, entity_id, cost=charge)

    if writeback_failures:
        # The job still completes (the lock must release), but the failures are
        # surfaced — both in the log and as items_processed < items_total on the
        # row — so a "complete" job with gaps is not mistaken for full success.
        logger.warning("wiki-gen job %s completed with %d writeback failure(s)",
                       job.job_id, writeback_failures)
    await repo.complete(job.job_id)
    return "complete"
