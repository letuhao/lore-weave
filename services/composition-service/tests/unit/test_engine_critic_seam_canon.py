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

⚠️ **This test pins a DEFECT, not a contract.** C2 grounds the seam in the roster canon, and
when it lands this test is INVERTED — it must then assert the rules arrive — never deleted.
A pin that is quietly dropped is how a fixed bug becomes an unfixed one again.
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


@pytest.fixture
def judged(monkeypatch):
    """Drive the REAL seam with its HTTP/LLM edges stubbed, and record the judge call."""
    import app.clients.book_client as book_client
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

    monkeypatch.setattr(book_client, "get_book_client", lambda: _Book())

    def _no_pool():
        # The seam resolves source-language best-effort and swallows failures; refusing here
        # keeps the test off the DB without hiding the path.
        raise RuntimeError("no pool in unit tests")

    monkeypatch.setattr(db_pool, "get_pool", _no_pool)
    return rec


async def test_the_headless_critic_seam_judges_with_NO_canon(judged):
    """THE DEFECT C2 CLOSES: the judge is handed zero rules and zero facts.

    So `canon_consistency` is a self-consistency reading of the passage — the same disease as
    `name_truth_source: prompt_proxy` one layer up, and the reason QC-5's inverted criterion
    cannot currently fail for the right reason.
    """
    from uuid import uuid4

    verdict = await EngineCriticSeam().critique(
        created_by=uuid4(), book_id=uuid4(), chapter_id=uuid4(), plan_run_id=uuid4(),
        params={"model_ref": str(uuid4()), "model_source": "user_model"},
    )

    assert judged.kwargs is not None, "the seam never reached the judge"
    assert judged.kwargs["active_rules"] == [], (
        "C2 has landed: the seam now carries canon rules — INVERT this test to assert they "
        "arrive, do not delete it"
    )
    assert judged.kwargs["present_facts"] == [], (
        "C2 has landed: the seam now carries canon facts — INVERT this test to assert they "
        "arrive, do not delete it"
    )
    # ...and the ungrounded judgement still lands as a normal verdict, which is exactly why
    # nothing downstream can tell it apart from a grounded one.
    assert verdict.severity == "ok"
    assert verdict.detail["canon_consistency"] == 5


async def test_the_seam_still_reaches_the_judge_with_the_passage(judged):
    """The counterweight: emptiness is about CANON, not about the seam being broken.

    Without this, the test above would also pass if the seam silently stopped judging
    altogether — an assertion that two things are empty is satisfied by nothing happening.
    """
    from uuid import uuid4

    await EngineCriticSeam().critique(
        created_by=uuid4(), book_id=uuid4(), chapter_id=uuid4(), plan_run_id=uuid4(),
        params={"model_ref": str(uuid4()), "model_source": "user_model"},
    )
    assert "betrayed" in judged.kwargs["passage"]
