"""Saga driver tests — batched per-stage dispatch, completion, cancellation."""

from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.saga.driver import process_campaign, reconcile_once, DispatchClients
from app.saga.gating import ChapterState
from app.clients.dispatch_clients import DispatchError
from tests.conftest import FakeRecord

USER = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
BOOK = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
CID = UUID("11111111-1111-1111-1111-111111111111")
PROJ = UUID("99999999-9999-9999-9999-999999999999")
C1 = "11111111-1111-1111-1111-111111111111"
C2 = "22222222-2222-2222-2222-222222222222"


def _campaign(**over):
    base = {
        "campaign_id": CID,
        "owner_user_id": USER,
        "book_owner_user_id": USER,   # E0-4b: owner-run by default (book_owner == owner)
        "embedding_model_ref": None,
        "book_id": BOOK,
        "status": "running",
        "stages": ["knowledge", "translation", "eval"],
        "gating_mode": "cold_start",
        "knowledge_project_id": PROJ,
        "chapter_from": None,
        "chapter_to": None,
        "knowledge_model_source": "user_model",
        "knowledge_model_ref": None,
        "translation_model_source": "user_model",
        "translation_model_ref": None,
        "verifier_model_source": None,
        "verifier_model_ref": None,
        "eval_judge_model_source": None,
        "eval_judge_model_ref": None,
        "target_language": "vi",
    }
    base.update(over)
    return FakeRecord(base)


def _ch(cid, k="pending", t="pending", ka=0, ta=0):
    return ChapterState(cid, k, t, ka, ta)


def _clients():
    tr = AsyncMock()
    tr.dispatch_job = AsyncMock(return_value="job-1")
    kn = AsyncMock()
    kn.dispatch_extraction = AsyncMock(return_value="ext-1")
    return DispatchClients(translation=tr, knowledge=kn), tr, kn


@pytest.fixture
def patch_repo(mocker):
    m = {
        "load_chapter_states": mocker.patch(
            "app.saga.driver.repo.load_chapter_states", new_callable=AsyncMock),
        "count_inflight": mocker.patch(
            "app.saga.driver.repo.count_inflight", new_callable=AsyncMock, return_value=0),
        "mark_stage_dispatched": mocker.patch(
            "app.saga.driver.repo.mark_stage_dispatched", new_callable=AsyncMock),
        "mark_stage_failed": mocker.patch(
            "app.saga.driver.repo.mark_stage_failed", new_callable=AsyncMock),
        "set_campaign_status": mocker.patch(
            "app.saga.driver.repo.set_campaign_status", new_callable=AsyncMock),
        # S3c-2 cancel-propagation + job-id tracking
        "set_dispatched_job_id": mocker.patch(
            "app.saga.driver.repo.set_dispatched_job_id", new_callable=AsyncMock),
        "inflight_translation_job_ids": mocker.patch(
            "app.saga.driver.repo.inflight_translation_job_ids",
            new_callable=AsyncMock, return_value=[]),
        "has_inflight_knowledge": mocker.patch(
            "app.saga.driver.repo.has_inflight_knowledge",
            new_callable=AsyncMock, return_value=False),
        "mark_dispatched_stages_cancelled": mocker.patch(
            "app.saga.driver.repo.mark_dispatched_stages_cancelled", new_callable=AsyncMock),
    }
    return m


async def _process(pool, clients, campaign, *, max_attempts=3, max_inflight=20,
                   stuck_timeout_s=900):
    await process_campaign(
        pool, clients, campaign,
        max_attempts=max_attempts, max_inflight=max_inflight,
        stuck_timeout_s=stuck_timeout_s,
    )


async def test_cold_start_dispatches_both_stages(fake_pool, patch_repo):
    # c1 knowledge done → translate c1; c2 pending → extract.
    patch_repo["load_chapter_states"].return_value = [
        _ch(C1, k="done"), _ch(C2, k="pending"),
    ]
    clients, tr, kn = _clients()
    VER = "77777777-7777-7777-7777-777777777777"
    EJ = "88888888-8888-8888-8888-888888888888"
    await _process(fake_pool, clients,
                   _campaign(verifier_model_source="user_model", verifier_model_ref=VER,
                             eval_judge_model_source="user_model", eval_judge_model_ref=EJ))

    tr.dispatch_job.assert_awaited_once()
    assert tr.dispatch_job.call_args.kwargs["chapter_ids"] == [C1]
    kn.dispatch_extraction.assert_awaited_once()
    # S4a: both dispatches carry the campaign_id for cost attribution.
    assert tr.dispatch_job.call_args.kwargs["campaign_id"] == str(CID)
    assert kn.dispatch_extraction.call_args.kwargs["campaign_id"] == str(CID)
    # S5b: the campaign's verifier model is threaded onto the translation dispatch.
    assert tr.dispatch_job.call_args.kwargs["verifier_model_source"] == "user_model"
    assert tr.dispatch_job.call_args.kwargs["verifier_model_ref"] == VER
    # S5b-eval: the campaign's eval-judge model is threaded too.
    assert tr.dispatch_job.call_args.kwargs["eval_judge_model_source"] == "user_model"
    assert tr.dispatch_job.call_args.kwargs["eval_judge_model_ref"] == EJ
    # Both claimed rows flipped to dispatched.
    stages = {c.args[3] for c in patch_repo["mark_stage_dispatched"].call_args_list}
    assert stages == {"knowledge", "translation"}


BOOK_OWNER = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
EMB_REF = "44444444-4444-4444-4444-444444444444"


async def test_owner_run_dispatch_has_no_billing_split(fake_pool, patch_repo):
    # E0-4b: an owner-run campaign (book_owner == owner) dispatches knowledge under
    # the owner with NO billing split (legacy owner-paid path).
    patch_repo["load_chapter_states"].return_value = [_ch(C1, k="pending")]
    clients, tr, kn = _clients()
    await _process(fake_pool, clients, _campaign())  # book_owner_user_id defaults to USER
    kw = kn.dispatch_extraction.call_args.kwargs
    assert kw["user_id"] == str(USER)          # graph partition = owner
    assert kw["billing_user_id"] is None        # no split
    assert kw["billing_embedding_model"] is None


async def test_collaborator_dispatch_dual_identity(fake_pool, patch_repo):
    # E0-4b dual identity: a manage-collaborator's campaign (owner=caller, book_owner
    # differs) dispatches knowledge under the BOOK OWNER (graph) but bills the CALLER
    # (their key + same-model embedding ref). Translation stays caller-attributed.
    patch_repo["load_chapter_states"].return_value = [_ch(C1, k="pending"), _ch(C2, k="done")]
    clients, tr, kn = _clients()
    await _process(fake_pool, clients,
                   _campaign(book_owner_user_id=BOOK_OWNER, embedding_model_ref=UUID(EMB_REF)))
    # knowledge: graph = book owner, billing = caller (the campaign owner), caller's emb ref.
    kw = kn.dispatch_extraction.call_args.kwargs
    assert kw["user_id"] == str(BOOK_OWNER)
    assert kw["billing_user_id"] == str(USER)
    assert kw["billing_embedding_model"] == EMB_REF
    # translation: caller-attributed (= campaign owner), no book-owner identity leak.
    assert tr.dispatch_job.call_args.kwargs["user_id"] == str(USER)


async def test_completion_sets_completed(fake_pool, patch_repo):
    patch_repo["load_chapter_states"].return_value = [_ch(C1, k="done", t="done")]
    clients, tr, kn = _clients()
    await _process(fake_pool, clients, _campaign())
    patch_repo["set_campaign_status"].assert_awaited_once()
    assert patch_repo["set_campaign_status"].call_args.args[2] == "completed"
    tr.dispatch_job.assert_not_called()
    kn.dispatch_extraction.assert_not_called()


async def test_cancelling_propagates_and_finalizes(fake_pool, patch_repo):
    # S3c-2: cancelling ACTIVELY cancels in-flight jobs then finalizes (no passive
    # drain). Translation cancelled per in-flight job_id; knowledge per project.
    patch_repo["load_chapter_states"].return_value = [_ch(C1, k="dispatched")]
    patch_repo["inflight_translation_job_ids"].return_value = [UUID("aaaaaaaa-0000-0000-0000-000000000001")]
    patch_repo["has_inflight_knowledge"].return_value = True
    clients, tr, kn = _clients()
    tr.cancel_job = AsyncMock()
    kn.cancel_extraction = AsyncMock()

    await _process(fake_pool, clients, _campaign(status="cancelling"))

    tr.cancel_job.assert_awaited_once()  # in-flight translation job cancelled
    kn.cancel_extraction.assert_awaited_once()  # project extraction cancelled
    patch_repo["mark_dispatched_stages_cancelled"].assert_awaited_once()  # terminalize
    assert patch_repo["set_campaign_status"].call_args.args[2] == "cancelled"
    # NOT dispatching new work while cancelling
    tr.dispatch_job.assert_not_called()
    kn.dispatch_extraction.assert_not_called()


async def test_cancelling_reads_inflight_before_terminalizing(fake_pool, patch_repo):
    # ORDER invariant (the correctness lynchpin): in-flight translation job_ids
    # must be read BEFORE mark_dispatched_stages_cancelled flips those rows to
    # failed — else the cancel set is empty and the jobs orphan. Lock it.
    seen = {}

    async def _inflight(pool, campaign_id):
        seen["mark_awaits_when_inflight_read"] = \
            patch_repo["mark_dispatched_stages_cancelled"].await_count
        return [UUID("aaaaaaaa-0000-0000-0000-000000000001")]

    patch_repo["inflight_translation_job_ids"].side_effect = _inflight
    patch_repo["load_chapter_states"].return_value = [_ch(C1, k="dispatched")]
    clients, tr, kn = _clients()
    tr.cancel_job = AsyncMock()
    await _process(fake_pool, clients, _campaign(status="cancelling"))
    assert seen["mark_awaits_when_inflight_read"] == 0  # mark had NOT run yet


async def test_cancelling_propagate_failure_still_finalizes(fake_pool, patch_repo):
    # Best-effort: a downstream cancel error must not block finalization.
    patch_repo["load_chapter_states"].return_value = [_ch(C1, k="dispatched")]
    patch_repo["inflight_translation_job_ids"].return_value = [UUID("aaaaaaaa-0000-0000-0000-000000000001")]
    clients, tr, kn = _clients()
    tr.cancel_job = AsyncMock(side_effect=DispatchError("translation down"))
    await _process(fake_pool, clients, _campaign(status="cancelling"))
    patch_repo["mark_dispatched_stages_cancelled"].assert_awaited_once()
    assert patch_repo["set_campaign_status"].call_args.args[2] == "cancelled"


async def test_dispatch_records_job_id_for_cancel(fake_pool, patch_repo):
    # S3c-2: a successful dispatch records the job_id so cancel can target it.
    patch_repo["load_chapter_states"].return_value = [_ch(C1, k="done")]  # translate c1
    clients, tr, kn = _clients()
    tr.dispatch_job = AsyncMock(return_value="job-xyz")
    await _process(fake_pool, clients, _campaign())
    set_calls = [c for c in patch_repo["set_dispatched_job_id"].call_args_list
                 if c.args[3] == "translation"]
    assert set_calls and set_calls[0].args[4] == "job-xyz"


async def test_knowledge_without_project_marks_failed(fake_pool, patch_repo):
    patch_repo["load_chapter_states"].return_value = [_ch(C1, k="pending")]
    clients, tr, kn = _clients()
    await _process(fake_pool, clients, _campaign(knowledge_project_id=None))
    kn.dispatch_extraction.assert_not_called()
    patch_repo["mark_stage_failed"].assert_awaited()
    assert patch_repo["mark_stage_failed"].call_args.args[3] == "knowledge"


async def test_dispatch_error_marks_failed(fake_pool, patch_repo):
    patch_repo["load_chapter_states"].return_value = [_ch(C1, k="done")]
    clients, tr, kn = _clients()
    tr.dispatch_job = AsyncMock(side_effect=DispatchError("boom"))
    await _process(fake_pool, clients, _campaign())
    # CLAIM-FIRST invariant (double-spend guard): the row was marked `dispatched`
    # BEFORE the dispatch call that failed, then released to `failed`.
    dispatched_translation = [
        c for c in patch_repo["mark_stage_dispatched"].call_args_list
        if c.args[3] == "translation"
    ]
    assert dispatched_translation, "row must be claimed before dispatch (claim-first)"
    patch_repo["mark_stage_failed"].assert_awaited()
    assert patch_repo["mark_stage_failed"].call_args.args[3] == "translation"


async def test_inflight_ceiling_blocks_new_dispatch(fake_pool, patch_repo):
    # At the per-campaign in-flight ceiling → no new dispatch this tick.
    patch_repo["load_chapter_states"].return_value = [
        _ch(C1, k="pending"), _ch(C2, k="pending"),
    ]
    patch_repo["count_inflight"].return_value = 20  # == max_inflight
    clients, tr, kn = _clients()
    await _process(fake_pool, clients, _campaign(), max_inflight=20)
    tr.dispatch_job.assert_not_called()
    kn.dispatch_extraction.assert_not_called()


async def test_reconcile_claims_not_lists(fake_pool, mocker):
    # S3c HA: reconcile must CLAIM (lease) campaigns, not plain-list them — so
    # peer replicas don't double-process. Lock the claim wiring.
    claim = mocker.patch("app.saga.driver.repo.claim_active_campaigns",
                         new_callable=AsyncMock, return_value=[])
    listed = mocker.patch("app.saga.driver.repo.list_active_campaigns",
                          new_callable=AsyncMock, return_value=[])
    clients, _, _ = _clients()
    await reconcile_once(fake_pool, clients, driver_id="drv-1", max_attempts=3,
                         max_inflight=20, stuck_timeout_s=900)
    claim.assert_awaited_once()
    listed.assert_not_called()
    # claim is owner-scoped (renew own / exclude peers) + leased > tick
    assert claim.call_args.kwargs["driver_id"] == "drv-1"
    assert claim.call_args.kwargs["lease_seconds"] >= 30


async def test_reconcile_processes_each_claimed_campaign(fake_pool, mocker):
    # Lock the claim→process wiring: every CLAIMED campaign is processed this tick.
    c1, c2 = _campaign(), _campaign(status="cancelling")
    mocker.patch("app.saga.driver.repo.claim_active_campaigns",
                 new_callable=AsyncMock, return_value=[c1, c2])
    proc = mocker.patch("app.saga.driver.process_campaign", new_callable=AsyncMock)
    clients, _, _ = _clients()
    await reconcile_once(fake_pool, clients, driver_id="d", max_attempts=3,
                         max_inflight=20, stuck_timeout_s=900)
    assert proc.await_count == 2


async def test_dispatched_rows_not_redispatched(fake_pool, patch_repo):
    # Everything already in-flight → no new dispatch (double-spend guard).
    patch_repo["load_chapter_states"].return_value = [
        _ch(C1, k="dispatched"), _ch(C2, k="done", t="dispatched"),
    ]
    clients, tr, kn = _clients()
    await _process(fake_pool, clients, _campaign())
    tr.dispatch_job.assert_not_called()
    kn.dispatch_extraction.assert_not_called()


# ── D-CAMPAIGN-BESTEFFORT-EMIT-REDIS: stuck-reconcile is actually WIRED ──────
# (nil-tolerant wiring guard: a dropped reconcile_stuck call would silently
# no-op and every other test would stay green — assert the call site fires.)

async def test_reconcile_stuck_runs_before_gating_on_running(fake_pool, patch_repo, mocker):
    spy = mocker.patch("app.saga.driver.reconcile_stuck", new_callable=AsyncMock)
    patch_repo["load_chapter_states"].return_value = [_ch(C1, k="pending")]
    clients, tr, kn = _clients()
    await _process(fake_pool, clients, _campaign(), stuck_timeout_s=900)
    spy.assert_awaited_once()
    # threaded the configured timeout, and ran BEFORE states were loaded for gating
    assert spy.call_args.kwargs["timeout_s"] == 900
    assert spy.await_count == 1
    assert patch_repo["load_chapter_states"].await_count == 1


async def test_reconcile_stuck_skipped_when_cancelling(fake_pool, patch_repo, mocker):
    # A cancelling campaign is tearing down, not self-healing — reconcile must not run.
    spy = mocker.patch("app.saga.driver.reconcile_stuck", new_callable=AsyncMock)
    patch_repo["load_chapter_states"].return_value = [_ch(C1, k="dispatched")]
    clients, tr, kn = _clients()
    tr.cancel_job = AsyncMock()
    await _process(fake_pool, clients, _campaign(status="cancelling"))
    spy.assert_not_awaited()
