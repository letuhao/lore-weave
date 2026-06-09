"""S4a — worker-ai cost-attribution chokepoint.

Mirrors translation-service's test: a campaign bound on the task (set_campaign_id)
must land in EVERY provider job's job_meta via the central submit_and_wait merge,
so no extraction call site in loreweave_extraction can silently drop attribution.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.llm_client import LLMClient, set_campaign_id


class _FakeSubmit:
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id


def _fake_sdk():
    sdk = AsyncMock()
    sdk.submit_job = AsyncMock(return_value=_FakeSubmit("job-1"))
    sdk.wait_terminal = AsyncMock(return_value=object())
    return sdk


async def test_submit_and_wait_stamps_campaign_id_from_contextvar():
    sdk = _fake_sdk()
    client = LLMClient(sdk)
    set_campaign_id("camp-123")
    try:
        await client.submit_and_wait(
            user_id="u", operation="entity_extraction",
            model_source="user_model", model_ref="m",
            input={"messages": []}, job_meta={"stage": "extract"},
        )
    finally:
        set_campaign_id(None)
    req = sdk.submit_job.call_args.args[0]
    assert req.job_meta["campaign_id"] == "camp-123"
    assert req.job_meta["stage"] == "extract"  # caller key preserved


async def test_submit_and_wait_no_campaign_id_when_unset():
    set_campaign_id(None)
    sdk = _fake_sdk()
    client = LLMClient(sdk)
    await client.submit_and_wait(
        user_id="u", operation="entity_extraction",
        model_source="user_model", model_ref="m",
        input={}, job_meta={"stage": "extract"},
    )
    req = sdk.submit_job.call_args.args[0]
    assert "campaign_id" not in (req.job_meta or {})


def test_submit_job_only_invoked_via_wrapper():
    """S4a drift guard (review-impl LOW-2): the campaign_id merge lives ONLY in
    LLMClient.submit_and_wait. A future direct SDK submit_job call (e.g. from
    loreweave_extraction wiring or runner) would bypass attribution silently.
    Lock it: `.submit_job(` appears only in llm_client.py."""
    import pathlib

    app_dir = pathlib.Path(__file__).resolve().parent.parent / "app"
    offenders = [
        str(p.relative_to(app_dir))
        for p in app_dir.rglob("*.py")
        if p.name != "llm_client.py" and ".submit_job(" in p.read_text(encoding="utf-8")
    ]
    assert not offenders, (
        f"submit_job called outside the llm_client wrapper (bypasses campaign "
        f"attribution): {offenders}"
    )
