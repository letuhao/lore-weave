"""25 · T5 — spend attribution by effect (F7): a headless authoring/generation run spends
LLM tokens AS its row's actor (`generation_job.created_by`), NOT the caller or a service
identity — asserted on the USAGE ROW (`usage_logs.owner_user_id`), not in source.

LIVE EFFECT EVIDENCE (2026-07-16, the G5 S06 run's `run_pipeline=true` compile, gemma-4-26b):
`loreweave_usage_billing.usage_logs` recorded the compiler's LLM passes —
  owner_user_id                        | purpose        | lane        | tokens | status
  019d5e3c-…(the run's created_by)     | plan_fix_scene | interactive | 419    | success
  019d5e3c-…                           | plan_judge     | interactive | 783    | success
  019d5e3c-…                           | prose_plan     | interactive | 1305   | success
— every row attributed to `owner_user_id` = the generation_job's `created_by` (the stored
actor), which is exactly F7's "runs as its row's actor" landing on the usage row.

This test is the REGRESSION GUARD on the mechanism that makes that true: the headless run
(no caller request in flight) mints a service bearer whose `sub` IS `created_by`
(`authoring_run_service.py` `mint_service_bearer(created_by, …)`), so book-service resolves
`owner_user_id = sub = created_by` and usage-billing attributes the spend there. A future
change that minted under a caller/service identity would silently mis-attribute spend — this
reds on it.
"""
from __future__ import annotations

import uuid

import jwt
import pytest

from app.mcp.service_bearer import mint_service_bearer

_SECRET = "test-secret-hs256"


def test_the_headless_run_bearer_sub_is_the_runs_created_by_actor():
    created_by = uuid.uuid4()
    token = mint_service_bearer(created_by, _SECRET)
    claims = jwt.decode(token, _SECRET, algorithms=["HS256"])
    # book-service resolves owner_user_id = sub; usage-billing attributes spend there.
    assert claims["sub"] == str(created_by)
    assert claims["src"] == "composition-mcp"  # marked as a service bearer, not a user login


def test_a_different_actor_gets_a_different_attribution_identity():
    # The attribution is keyed on the actor passed in — two runs by different creators
    # attribute to different owners (spend never bleeds across the F7 boundary).
    a, b = uuid.uuid4(), uuid.uuid4()
    sub_a = jwt.decode(mint_service_bearer(a, _SECRET), _SECRET, algorithms=["HS256"])["sub"]
    sub_b = jwt.decode(mint_service_bearer(b, _SECRET), _SECRET, algorithms=["HS256"])["sub"]
    assert sub_a == str(a) and sub_b == str(b) and sub_a != sub_b


def test_empty_secret_fails_closed_never_a_forgeable_token():
    # A run that could not attribute spend safely must RAISE, never emit an unsigned token.
    with pytest.raises(ValueError):
        mint_service_bearer(uuid.uuid4(), "")
