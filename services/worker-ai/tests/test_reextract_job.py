"""WS-2.6a legs 2+3 (D17 memory amendment) — the CORRECTION re-extract orchestrator + consumer.

Proves the re-extract-from-the-corrected-ENTRY flow (D-R30) with fakes, no live stack:
  - `extract_facts_from_text` — facts from an entry body; map-failure is retryable; a blank completion
    surfaces model_no_output (not a silent no-op).
  - `reextract_and_reconcile` — queue (leg 2) runs BEFORE invalidate (leg 3); a removal (no facts) still
    invalidates the day; a compute failure reconciles NOTHING; the daily-cap pauses before spend; the
    NO-RESURRECTION property (a corrected body queues the corrected fact, never the superseded one).
  - `run_one_reextract_message` — malformed → ACK(drop); retryable error → NACK; reconciled → ACK.
"""

from __future__ import annotations

import json

from app import reextract_job
from app.distiller import extract_facts_from_text
from app.reextract_consumer import run_one_reextract_message


class FakeLLM:
    """Answers a map call ('MESSAGES:') with canned facts. Optionally fails or returns a blank."""

    def __init__(self, map_facts=None, *, fail=False, blank=False):
        self._map_facts = map_facts or []
        self._fail = fail
        self._blank = blank
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self._fail:
            raise RuntimeError("model down")
        if self._blank:
            return "   "
        return json.dumps({"facts": self._map_facts})


class FakeKnowledge:
    def __init__(self, *, queue_fail=False, invalidate_fail=False, invalidated=2):
        self._queue_fail = queue_fail
        self._invalidate_fail = invalidate_fail
        self._invalidated = invalidated
        self.order: list[str] = []
        self.queued_facts: list[dict] | None = None
        self.invalidate_calls: list[dict] = []

    async def queue_diary_facts(self, *, user_id, book_id, entry_date, facts):
        self.order.append("queue")
        self.queued_facts = facts
        if self._queue_fail:
            raise RuntimeError("inbox down")
        return {"queued": len(facts)}

    async def invalidate_diary_day(self, *, user_id, book_id, entry_date):
        self.order.append("invalidate")
        self.invalidate_calls.append({"user_id": user_id, "book_id": book_id, "entry_date": entry_date})
        if self._invalidate_fail:
            raise RuntimeError("neo4j down")
        return {"invalidated": self._invalidated}


class FakeBilling:
    def __init__(self, exhausted=False, fail=False):
        self._exhausted = exhausted
        self._fail = fail

    async def daily_cap_exhausted(self, *, user_id):
        if self._fail:
            raise RuntimeError("billing down")
        return self._exhausted


# ── extract_facts_from_text (leg 2 core) ──────────────────────────────────────


async def test_extract_facts_from_entry_body():
    llm = FakeLLM(map_facts=[{"kind": "person", "text": "Alice froze the budget",
                              "subject": "Alice", "predicate": "froze", "object": "the budget"}])
    out = await extract_facts_from_text("Today Alice froze the Q3 budget.", llm)
    assert out.error is None
    assert len(out.facts) == 1 and out.facts[0].subject == "Alice"
    # No reduce prompt is ever built — this is facts-only.
    assert all("FACTS:" not in p or "MESSAGES:" in p for p in llm.prompts)


async def test_extract_facts_empty_body_is_a_clean_noop():
    llm = FakeLLM(map_facts=[{"kind": "event", "text": "x"}])
    out = await extract_facts_from_text("   ", llm)
    assert out.error is None and out.facts == [] and out.chunks_processed == 0
    assert llm.prompts == []  # never called the model on an empty entry


async def test_extract_facts_map_failure_is_retryable():
    out = await extract_facts_from_text("Some corrected text.", FakeLLM(fail=True))
    assert out.error == "map_failed" and out.retryable is True and out.map_failures == 1


async def test_extract_facts_blank_completion_is_model_no_output():
    out = await extract_facts_from_text("Some corrected text.", FakeLLM(blank=True))
    assert out.error == "model_no_output" and out.retryable is False


# ── reextract_and_reconcile (legs 2 + 3 together) ─────────────────────────────


async def test_reconcile_queues_then_invalidates_in_order():
    llm = FakeLLM(map_facts=[{"kind": "person", "text": "Alice froze the budget", "subject": "Alice"}])
    kn = FakeKnowledge(invalidated=3)
    out = await reextract_job.reextract_and_reconcile(
        user_id="u1", book_id="b1", entry_date="2026-03-10",
        body="Alice froze the Q3 budget.", llm=llm, knowledge_client=kn,
    )
    assert out["status"] == "reconciled"
    assert out["facts_queued"] == 1 and out["facts_invalidated"] == 3
    # leg 2 (queue) BEFORE leg 3 (invalidate) — the intermediate-state safety property.
    assert kn.order == ["queue", "invalidate"]


async def test_no_resurrection_the_corrected_fact_is_queued_not_the_old_one():
    # The corrected ENTRY says Alice; the re-extract must queue Alice, never Minh. The old Minh fact is
    # retired by the invalidate leg (proven at the repo level in the knowledge suite).
    llm = FakeLLM(map_facts=[{"kind": "person", "text": "Alice froze the budget",
                              "subject": "Alice", "predicate": "froze", "object": "the budget"}])
    kn = FakeKnowledge()
    await reextract_job.reextract_and_reconcile(
        user_id="u1", book_id="b1", entry_date="2026-03-10",
        body="Correction: Alice froze the budget, not Minh.", llm=llm, knowledge_client=kn,
    )
    texts = " ".join(f["text"] for f in (kn.queued_facts or []))
    subjects = " ".join(f.get("subject", "") for f in (kn.queued_facts or []))
    assert "Alice" in subjects and "Alice" in texts
    assert "Minh" not in subjects  # the superseded subject is never re-proposed


async def test_a_removal_correction_still_invalidates_the_day():
    # The user corrected the entry so the day now has NO facts (they removed the only claim). The day's
    # OLD confirmed facts must STILL be invalidated — else the deleted fact survives in recall.
    kn = FakeKnowledge(invalidated=1)
    out = await reextract_job.reextract_and_reconcile(
        user_id="u1", book_id="b1", entry_date="2026-03-10",
        body="Nothing noteworthy happened.", llm=FakeLLM(map_facts=[]), knowledge_client=kn,
    )
    assert kn.order == ["invalidate"]  # nothing to queue, but the day is still reconciled
    assert out["facts_invalidated"] == 1 and out["status"] == "reconciled"


async def test_compute_failure_reconciles_nothing_and_is_retryable():
    kn = FakeKnowledge()
    out = await reextract_job.reextract_and_reconcile(
        user_id="u1", book_id="b1", entry_date="2026-03-10",
        body="Some corrected text.", llm=FakeLLM(fail=True), knowledge_client=kn,
    )
    assert out["status"] == "error" and out["retryable"] is True
    # CRITICAL: a partial extraction must NOT invalidate the day (that would strand the graph).
    assert kn.order == []


async def test_daily_cap_pauses_before_any_spend():
    llm = FakeLLM(map_facts=[{"kind": "event", "text": "x"}])
    kn = FakeKnowledge()
    out = await reextract_job.reextract_and_reconcile(
        user_id="u1", book_id="b1", entry_date="2026-03-10", body="text", llm=llm,
        knowledge_client=kn, billing_client=FakeBilling(exhausted=True),
    )
    assert out["status"] == "paused" and out["retryable"] is False
    assert llm.prompts == [] and kn.order == []  # no model, no reconcile


async def test_billing_error_fails_open_and_reconciles():
    llm = FakeLLM(map_facts=[{"kind": "event", "text": "x"}])
    kn = FakeKnowledge()
    out = await reextract_job.reextract_and_reconcile(
        user_id="u1", book_id="b1", entry_date="2026-03-10", body="text", llm=llm,
        knowledge_client=kn, billing_client=FakeBilling(fail=True),
    )
    assert out["status"] == "reconciled"  # fail-open: a down billing service never blocks memory


# ── run_one_reextract_message (consumer decode + ack contract) ────────────────


def _fields(**over):
    base = {
        "user_id": "u1", "book_id": "b1", "entry_date": "2026-03-10",
        "language": "en", "model_source": "byok", "model_ref": "m1",
        "body": "Alice froze the budget.",
    }
    base.update(over)
    return base


class _FakeLLMClient:
    """Stands in for worker-ai's LLMClient (make_distill_llm adapts it). Returns one map result."""

    async def submit_and_wait(self, **kwargs):
        class _Job:
            status = "completed"
            result = {"messages": [{"content": json.dumps({"facts": [{"kind": "person",
                       "text": "Alice froze the budget", "subject": "Alice"}]})}]}
        return _Job()


async def test_consumer_reconciled_acks():
    kn = FakeKnowledge()
    ack = await run_one_reextract_message(
        knowledge_client=kn, llm_client=_FakeLLMClient(), fields=_fields(),
    )
    assert ack is True and kn.order == ["queue", "invalidate"]


async def test_consumer_malformed_message_is_dropped():
    kn = FakeKnowledge()
    ack = await run_one_reextract_message(
        knowledge_client=kn, llm_client=_FakeLLMClient(), fields=_fields(body=""),
    )
    assert ack is True and kn.order == []  # poison ACKed, never processed


async def test_consumer_retryable_error_is_nacked():
    class _FailLLM:
        async def submit_and_wait(self, **kwargs):
            class _Job:
                status = "failed"
                error = "boom"
                result = None
            return _Job()

    kn = FakeKnowledge()
    ack = await run_one_reextract_message(
        knowledge_client=kn, llm_client=_FailLLM(), fields=_fields(),
    )
    assert ack is False and kn.order == []  # left un-acked for redelivery; nothing reconciled
