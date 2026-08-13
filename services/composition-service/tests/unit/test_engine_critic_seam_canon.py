"""C1 — what the D5 critic seam is actually handed as canon.

The real `EngineCriticSeam` had **no test at all**: every driver test in
`test_authoring_runs_service.py` injects `FakeCriticSeam` on purpose ("never the real
EngineCriticSeam — it fetches the draft over HTTP"), so the one thing the seam decides for
itself — *what canon the judge gets to compare the prose against* — was decided by nobody
and guarded by nothing.

It passes literal empty containers:

    critique = await judge_prose(
        ..., passage=text, active_rules=[], present_facts=[], profile=profile,
    )

The seam's own docstring calls this an honest v1 gap — *"this headless seam passes empty
active_rules/present_facts, so `canon_consistency` judges from the passage alone"* — and QC-5
is the task that has to care, because QC-5's acceptance assertion is **a misattributed betrayal
must not score 5/5**. A judge holding no canon cannot fail that assertion for the right reason.
Measured on the isolated stack 2026-08-13, one authoring run over the acceptance book's
chapter 11: `canon_consistency=5`, `violations=[]`, from empty canon.

✅ **C2 landed 2026-08-13 and this file was INVERTED, not deleted** — it now asserts the canon
ARRIVES, and that the seam still says which grounding it got. A pin that is quietly dropped
when the bug is fixed is how the bug comes back unobserved.
"""
from __future__ import annotations

import pytest

from app.services.authoring_run_service import EngineCriticSeam

pytestmark = pytest.mark.anyio


class _Recorder:
    """Captures the kwargs the seam hands the judge."""

    def __init__(self) -> None:
        self.kwargs: dict | None = None

    async def __call__(self, _llm, **kwargs):
        self.kwargs = kwargs
        return {"coherence": 5, "voice_match": 5, "pacing": 4, "canon_consistency": 5,
                "violations": []}


class _Kal:
    """A cast at the chapter's story position — what `state@as_of` returns."""

    def __init__(self, *, as_of_ok: bool = True) -> None:
        self.state_calls: list[int] = []
        self.roster_calls = 0
        self._as_of_ok = as_of_ok

    async def state(self, _book_id, *, as_of, user_id=None):
        # The real KAL returns the entity LIST directly (`[{entity_id, facts: [...]}]`) and
        # facts are keyed `attr` — a dict wrapper or a `fact_kind` key renders an EMPTY cast,
        # which is the C1 defect wearing a passing test.
        self.state_calls.append(as_of)
        return [{"entity_id": "e1", "facts": [
            {"attr": "name", "value": "Mira"},
            {"attr": "role", "value": "the betrayed heir"},
        ]}]

    async def roster(self, _book_id, *, user_id=None, strict=False):
        self.roster_calls += 1
        return [{"entity_id": "e1", "name": "Mira", "kind": None}]


@pytest.fixture
def judged(monkeypatch):
    """Drive the REAL seam with its HTTP/LLM edges stubbed, and record the judge call."""
    import app.clients.book_client as book_client
    import app.clients.kal_client as kal_client
    import app.clients.llm_client as llm_client
    import app.db.pool as db_pool
    import app.engine.critic as critic_mod
    import app.mcp.service_bearer as bearer_mod

    rec = _Recorder()
    monkeypatch.setattr(critic_mod, "judge_prose", rec)
    monkeypatch.setattr(bearer_mod, "mint_service_bearer", lambda *_a, **_k: "bearer")
    monkeypatch.setattr(llm_client, "get_llm_client", lambda: object())

    class _Book:
        async def get_draft(self, *_a, **_k):
            return {"body": {"type": "doc", "content": [
                {"type": "paragraph", "content": [
                    {"type": "text", "text": "Kai betrayed Mira at the gate."}]}]}}

        async def get_chapter_sort_orders(self, chapter_ids):
            return {str(chapter_ids[0]): 12}

        async def get_book(self, *_a, **_k):
            return {"genres": ["xianxia"]}

    kal = _Kal()
    monkeypatch.setattr(book_client, "get_book_client", lambda: _Book())
    monkeypatch.setattr(kal_client, "get_kal_client", lambda: kal)
    rec.kal = kal

    def _no_pool():
        # The seam resolves source-language best-effort and swallows failures; refusing here
        # keeps the test off the DB without hiding the path.
        raise RuntimeError("no pool in unit tests")

    monkeypatch.setattr(db_pool, "get_pool", _no_pool)
    return rec


async def test_the_critic_seam_judges_AGAINST_the_canon_bible(judged):
    """THE INVERTED PIN: the judge is handed the chapter's canon, read at its story position.

    Before C2 this was `present_facts=[]` and `canon_consistency` was a self-consistency
    reading of the passage — the same disease as `name_truth_source: prompt_proxy` one layer
    up, and the reason QC-5's criterion could not fail for the right reason.
    """
    from uuid import uuid4

    verdict = await EngineCriticSeam().critique(
        created_by=uuid4(), book_id=uuid4(), chapter_id=uuid4(), plan_run_id=uuid4(),
        params={"model_ref": str(uuid4()), "model_source": "user_model"},
    )

    assert judged.kwargs is not None, "the seam never reached the judge"
    facts = judged.kwargs["present_facts"]
    assert facts and "Mira" in facts[0], (
        "the seam is judging without canon again — this is the C1 defect returning"
    )
    # Read AS OF the chapter's sort_order, not the untimed roster: a bible built from the
    # roster describes the END of the book and is confidently wrong about chapter 12.
    assert judged.kal.state_calls == [12]
    assert judged.kal.roster_calls == 0
    # And the grounding rides the verdict, so a weakly-grounded score cannot pass for a
    # grounded one downstream.
    assert verdict.detail["canon_grounding"] == "as_of"
    assert verdict.detail["canon_as_of"] == 12


async def test_the_seam_still_reaches_the_judge_with_the_passage(judged):
    """The counterweight: the seam judges the PROSE, not only the bible.

    Kept from the C1 pin. It was there because "both lists are empty" is satisfied by nothing
    happening at all; it stays because "the bible arrived" would be satisfied by a seam that
    forgot the passage.
    """
    from uuid import uuid4

    await EngineCriticSeam().critique(
        created_by=uuid4(), book_id=uuid4(), chapter_id=uuid4(), plan_run_id=uuid4(),
        params={"model_ref": str(uuid4()), "model_source": "user_model"},
    )
    assert "betrayed" in judged.kwargs["passage"]


async def test_an_empty_cast_is_NOT_reported_as_grounded(judged, monkeypatch):
    """The live-run defect this cycle caught in its own instrumentation.

    A convention block renders with nobody in it, so the bible's text is non-empty even when
    the KAL returned nothing — and the first cut called that `as_of`. The run that exposed it
    had `grounding='as_of', cast_size=0` while the log said
    `kal state@11 unavailable: Name or service not known`: an OUTAGE laundered into a verdict
    that reads as grounded. `convention_only` is the honest label.
    """
    from uuid import uuid4

    async def _no_cast(*_a, **_k):
        return []

    monkeypatch.setattr(judged.kal, "state", _no_cast)

    verdict = await EngineCriticSeam().critique(
        created_by=uuid4(), book_id=uuid4(), chapter_id=uuid4(), plan_run_id=uuid4(),
        params={"model_ref": str(uuid4()), "model_source": "user_model"},
    )

    assert verdict.detail["canon_grounding"] == "convention_only"
    assert verdict.detail["canon_cast_size"] == 0


async def test_the_verdict_records_WHO_judged(judged):
    """C3 — S6 classifies the critic, and the classification rides the verdict.

    This seam was an EIGHTH hand-rolled copy of the anti-self-reinforcement rule and did not
    even implement it: it preferred `critic_model_ref`, silently fell back to the drafter, and
    told nobody which had happened. A `canon_consistency` produced by the drafter grading its
    own prose is a self-witness; one produced by an independent model is evidence. They were
    indistinguishable on the wire.
    """
    from uuid import uuid4

    drafter, critic_model = str(uuid4()), str(uuid4())
    verdict = await EngineCriticSeam().critique(
        created_by=uuid4(), book_id=uuid4(), chapter_id=uuid4(), plan_run_id=uuid4(),
        params={"model_ref": drafter, "model_source": "user_model",
                "critic_model_ref": critic_model, "critic_model_source": "user_model"},
    )
    assert verdict.detail["critic_status"] == "configured"
    assert verdict.detail["critic_ref"] == critic_model


async def test_a_self_witnessed_verdict_SAYS_SO(judged):
    """The counterweight, and the case that matters: no distinct critic configured.

    The seam still judges — an autonomous run has no human to re-ask, so "same-model critique
    is weaker but better than no net" is the deliberate policy, and it DIVERGES from the
    routers, which refuse. The divergence is allowed in what happens, never in what is known.
    """
    from uuid import uuid4

    drafter = str(uuid4())
    verdict = await EngineCriticSeam().critique(
        created_by=uuid4(), book_id=uuid4(), chapter_id=uuid4(), plan_run_id=uuid4(),
        params={"model_ref": drafter, "model_source": "user_model"},
    )
    assert verdict.detail["critic_status"] == "not_configured", (
        "the drafter graded its own prose and the verdict did not say so"
    )
    assert verdict.detail["critic_ref"] == drafter
