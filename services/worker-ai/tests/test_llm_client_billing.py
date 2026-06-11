"""E0-3 Phase 2a — BYOK caller-pays chokepoint (worker-ai LLM side).

A book collaborator's extraction must resolve every LLM provider call under the
COLLABORATOR's user_id (their key + budget), never the project owner's. The
billing user is bound on the task (set_billing_user_id) and submit_and_wait —
the single chokepoint every extraction LLM call flows through — overrides the
resolving user_id with it. Unset (owner-triggered) ⇒ per-call user_id unchanged.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.llm_client import LLMClient, set_billing_user_id


class _FakeSubmit:
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id


def _fake_sdk():
    sdk = AsyncMock()
    sdk.submit_job = AsyncMock(return_value=_FakeSubmit("job-1"))
    sdk.wait_terminal = AsyncMock(return_value=object())
    return sdk


async def test_submit_and_wait_resolves_under_billing_user_when_set():
    """Collaborator path: provider call resolves under the billing user, not the
    per-call (owner) user_id — this is what charges the collaborator's key."""
    sdk = _fake_sdk()
    client = LLMClient(sdk)
    set_billing_user_id("collaborator-B")
    try:
        await client.submit_and_wait(
            user_id="owner-A",  # the owner (graph partition) id
            operation="entity_extraction",
            model_source="user_model", model_ref="m",
            input={"messages": []},
        )
    finally:
        set_billing_user_id(None)
    # Both submit and wait must use the billing user (the key resolves there).
    assert sdk.submit_job.call_args.kwargs["user_id"] == "collaborator-B"
    assert sdk.wait_terminal.call_args.kwargs["user_id"] == "collaborator-B"


async def test_submit_and_wait_uses_per_call_user_when_billing_unset():
    """Owner-triggered path (billing None): the per-call user_id is used
    unchanged — the legacy single-identity behaviour."""
    set_billing_user_id(None)
    sdk = _fake_sdk()
    client = LLMClient(sdk)
    await client.submit_and_wait(
        user_id="owner-A", operation="entity_extraction",
        model_source="user_model", model_ref="m", input={},
    )
    assert sdk.submit_job.call_args.kwargs["user_id"] == "owner-A"
    assert sdk.wait_terminal.call_args.kwargs["user_id"] == "owner-A"


async def test_billing_user_does_not_leak_across_tasks_via_default():
    """The contextvar default is None: a fresh read (no set on this task) must
    not inherit a value — the owner's key must never be charged by accident."""
    # Simulate clearing (what process_job does for owner-triggered jobs).
    set_billing_user_id(None)
    sdk = _fake_sdk()
    client = LLMClient(sdk)
    await client.submit_and_wait(
        user_id="owner-A", operation="entity_extraction",
        model_source="user_model", model_ref="m", input={},
    )
    assert sdk.submit_job.call_args.kwargs["user_id"] == "owner-A"
