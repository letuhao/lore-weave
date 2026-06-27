"""Public MCP-key spend attribution carrier (P4/Wave-C slice D).

Covers loreweave_llm.attribution (the contextvar bridge) + its merge into the
submit_job wire body. Uses httpx.MockTransport so submit_job runs in-memory.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from loreweave_llm import (
    Client,
    get_public_key_attribution,
    merge_attribution_into_job_meta,
    set_public_key_attribution,
)
from loreweave_llm.attribution import _mcp_key_id_ctx, _spend_cap_usd_ctx
from loreweave_llm.models import SubmitJobRequest

VALID_UUID = "019d5e3c-1234-7890-abcd-1344e148bf7c"
JOB_UUID = "019d5e3c-aaaa-bbbb-cccc-dddddddddddd"


@pytest.fixture(autouse=True)
def _reset_attribution():
    """Each test starts + ends with a CLEARED carrier — a leaked contextvar would
    cross-contaminate other tests (the very leak this carrier must avoid)."""
    set_public_key_attribution(None, None)
    yield
    set_public_key_attribution(None, None)


# ── merge_attribution_into_job_meta ──────────────────────────────────────


def test_merge_no_key_returns_same_object():
    meta = {"campaign_id": "c1"}
    # No public key in scope → identity-unchanged (caller can detect "no change").
    assert merge_attribution_into_job_meta(meta) is meta
    assert merge_attribution_into_job_meta(None) is None


def test_merge_adds_key_and_cap_preserving_other_keys():
    set_public_key_attribution("key-xyz", 5.0)
    out = merge_attribution_into_job_meta({"campaign_id": "c1"})
    assert out == {"campaign_id": "c1", "mcp_key_id": "key-xyz", "spend_cap_usd": 5.0}


def test_merge_omits_cap_when_none_but_keeps_key():
    set_public_key_attribution("key-xyz", None)
    out = merge_attribution_into_job_meta(None)
    assert out == {"mcp_key_id": "key-xyz"}
    assert "spend_cap_usd" not in out


def test_merge_overwrites_caller_supplied_attribution():
    # SECURITY: a public agent must not spoof its own key id / raise its own cap by
    # stuffing job_meta — the server-set value WINS.
    set_public_key_attribution("real-key", 1.0)
    out = merge_attribution_into_job_meta({"mcp_key_id": "spoofed", "spend_cap_usd": 9999.0})
    assert out["mcp_key_id"] == "real-key"
    assert out["spend_cap_usd"] == 1.0


def test_set_then_clear():
    set_public_key_attribution("k", 2.0)
    assert get_public_key_attribution() == ("k", 2.0)
    set_public_key_attribution(None, None)
    assert get_public_key_attribution() == (None, None)
    assert _mcp_key_id_ctx.get() is None and _spend_cap_usd_ctx.get() is None


# ── submit_job folds the carrier into the wire body ──────────────────────


def _capture_client(captured: dict[str, Any]) -> Client:
    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(
            202,
            json={"job_id": JOB_UUID, "status": "pending", "submitted_at": "2026-06-28T00:00:00.0Z"},
        )

    return Client(
        base_url="http://gateway.test",
        auth_mode="internal",
        internal_token="svc-token",
        user_id="00000000-0000-0000-0000-000000000001",
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_submit_job_merges_attribution_into_body():
    captured: dict[str, Any] = {}
    client = _capture_client(captured)
    set_public_key_attribution("key-xyz", 3.5)
    await client.submit_job(
        SubmitJobRequest(
            operation="entity_extraction", model_source="user_model",
            model_ref=VALID_UUID, input={"messages": []}, job_meta={"campaign_id": "c1"},
        ),
    )
    jm = captured["body"]["job_meta"]
    assert jm["mcp_key_id"] == "key-xyz"
    assert jm["spend_cap_usd"] == 3.5
    assert jm["campaign_id"] == "c1"  # composes with the campaign carrier


@pytest.mark.asyncio
async def test_submit_job_first_party_carries_no_attribution():
    captured: dict[str, Any] = {}
    client = _capture_client(captured)
    # No public key set (first-party) → job_meta omitted entirely (exclude_none).
    await client.submit_job(
        SubmitJobRequest(
            operation="entity_extraction", model_source="user_model",
            model_ref=VALID_UUID, input={"messages": []},
        ),
    )
    assert "job_meta" not in captured["body"]
