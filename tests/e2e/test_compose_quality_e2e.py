"""E2E — the composition QUALITY surfaces through the real gateway + worker.

Unlike the (retired) hand-fed live-smoke scripts, these drive the ACTUAL endpoints
with the claude-test account against a real book, so every resolution step runs:
auth → outline/plan render → chapter assembly → canon → LLM judge → job poll. This is
the path that hid the `_render_outline_plan` ordering bug a crafted-input smoke sailed
past.

Skips when the local stack isn't up (gateway /health) so unit runs are unaffected.
LLM calls route to the account's BYOK model — needs LM Studio (or the BYOK backend)
reachable; a job that never completes surfaces as a TimeoutError, not a false green.

Run: `python -m pytest tests/e2e/test_compose_quality_e2e.py -v`
"""

from __future__ import annotations

from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio

import quality_harness as qh


@pytest_asyncio.fixture
async def qclient() -> AsyncIterator[httpx.AsyncClient]:
    """A gateway client with generous timeout headroom (the enqueue POST + each poll GET
    are fast; the LLM latency is absorbed by the poll loop). Skips if the stack is down."""
    async with httpx.AsyncClient(base_url=qh.GATEWAY_URL, timeout=60.0) as client:
        try:
            r = await client.get("/health")
            if r.status_code != 200:
                pytest.skip(f"gateway /health = {r.status_code}")
        except httpx.RequestError as exc:
            pytest.skip(f"gateway unreachable: {exc}")
        yield client


@pytest_asyncio.fixture
async def ctx(qclient: httpx.AsyncClient):
    """(client, headers, target) — logged in as claude-test with a resolved real target."""
    token = await qh.login(qclient)
    headers = qh.auth_headers(token)
    try:
        target = await qh.resolve_target(qclient, headers=headers)
    except RuntimeError as exc:
        pytest.skip(f"no drivable target for the test account: {exc}")
    return qclient, headers, target


@pytest.mark.asyncio
async def test_resolve_target_discovers_a_real_work(ctx):
    """The black-box discovery chain (books → work → chapter → model) yields a complete,
    plausibly-shaped target — the foundation every quality E2E stands on."""
    _client, _headers, t = ctx
    assert t.project_id and t.book_id and t.chapter_id and t.model_ref
    # UUIDs, not empty/placeholder
    assert len(t.project_id) >= 32 and len(t.chapter_id) >= 32 and len(t.model_ref) >= 32


@pytest.mark.asyncio
async def test_promise_coverage_e2e(ctx):
    """Book-level promise coverage through the real endpoint: the outline is rendered to
    plan_text (the path the smoke skipped), every chapter's prose assembled, a tracked set
    extracted, and the book scored. Asserts the v2 coverage shape came back."""
    client, headers, t = ctx
    cov = await qh.promise_coverage(client, t, headers=headers)
    for key in ("tracked_count", "paid_count", "abandoned_count", "absent_count",
                "pay_rate", "abandon_rate", "coverage"):
        assert key in cov, f"promise coverage missing '{key}': {cov}"
    assert isinstance(cov["coverage"], list)
    # counts are consistent with the verdict list (no fabricated totals)
    verdicts = [c.get("verdict") for c in cov["coverage"]]
    assert cov["abandoned_count"] == verdicts.count("abandoned")
    assert cov["paid_count"] == verdicts.count("paid")


@pytest.mark.asyncio
async def test_quality_report_e2e(ctx):
    """Per-chapter Quality Report through the real endpoint: 4-dim critic + promise audit."""
    client, headers, t = ctx
    rep = await qh.quality_report(client, t, headers=headers)
    assert "critic" in rep and "promises" in rep, f"unexpected report shape: {rep}"
    critic = rep["critic"]
    # either it scored (dims present) or it degraded with an explicit error — never silent
    assert "error" in critic or any(critic.get(d) is not None
                                    for d in ("coherence", "voice_match", "pacing", "canon_consistency"))
    assert "dropped" in rep["promises"] or "error" in rep["promises"]


@pytest.mark.asyncio
async def test_self_heal_propose_e2e(ctx):
    """Self-heal PROPOSE through the real endpoint: returns apply-ready proposals (read-only —
    the E2E never applies them). Proves the resolve (draft → text → canon) + judge path."""
    client, headers, t = ctx
    res = await qh.propose_self_heal(client, t, headers=headers)
    assert "proposals" in res, f"unexpected propose shape: {res}"
    assert isinstance(res["proposals"], list)
    for p in res["proposals"]:  # each proposal is apply-shaped
        assert {"id", "before", "after", "start", "end"} <= set(p)
