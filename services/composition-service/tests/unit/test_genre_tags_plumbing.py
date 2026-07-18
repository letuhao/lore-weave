"""27 PF-15 — `genre_tags` plumbing: route → service → repo → row → back out.

A field that the DB stores but no caller can SET is write-only; a field the DB stores but no
response RETURNS is indistinguishable from one that was dropped. Both are the same bug wearing
different clothes, and this repo has shipped it (`rest-write-mirror-drops-fields-the-mcp-tool-
accepts`: Pydantic's default `extra='ignore'` silently discards an undeclared write field, so the
client gets a 200 and the value evaporates).

So this proves the whole chain, not just one hop.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

from app.db.models import PlanRun
from app.db.repositories.plan_runs import PlanRunsRepo
from app.routers.plan_forge import PlanRunCreate
from app.services.plan_forge_service import PlanForgeService

REPO_SRC = Path(inspect.getfile(PlanRunsRepo)).read_text(encoding="utf-8")


# ── the write path: a client can actually SET it ──────────────────────────────


def test_the_request_model_DECLARES_genre_tags():
    """Undeclared ⇒ Pydantic's `extra='ignore'` drops it silently: the client sends genre_tags,
    gets a 200, and the plan is written genre-blind. Declaring it IS the fix."""
    assert "genre_tags" in PlanRunCreate.model_fields
    body = PlanRunCreate(source_markdown="x", mode="llm", genre_tags=["xianxia", "romance"])
    assert body.genre_tags == ["xianxia", "romance"]


def test_it_defaults_to_empty_not_null():
    assert PlanRunCreate(source_markdown="x", mode="rules").genre_tags == []


def test_the_service_accepts_it():
    sig = inspect.signature(PlanForgeService.create_run)
    assert "genre_tags" in sig.parameters


def test_the_repo_INSERTS_it_rather_than_defaulting_the_column():
    # The column has a DB default of '[]'. A create that never names it would ALWAYS store [] no
    # matter what the caller sent — a silent drop that no test of the request model would catch.
    assert "genre_tags" in inspect.signature(PlanRunsRepo.create).parameters
    assert "genre_tags)" in REPO_SRC       # named in the INSERT column list
    assert "$8::jsonb" in REPO_SRC          # …and bound as a real parameter


# ── the read path: it comes back out ──────────────────────────────────────────


def test_the_repo_SELECTS_it_back():
    """A column written but never selected validates to the model's default on every read — so the
    value is in the DB and invisible to the entire application. Write-only, with extra steps."""
    assert "pass_state, genre_tags" in REPO_SRC


def test_jsonb_columns_are_DECODED_not_left_as_strings():
    # asyncpg hands JSONB back as `str` unless a codec is registered. A column selected but not
    # decoded validates as a string and then silently becomes the model's default.
    #
    # Assert each key is IN the decode loop rather than matching the loop's exact literal: the
    # tuple legitimately grows (it since gained "grounded_on"), and a guard that reds on a correct
    # extension trains people to edit the guard. Dropping a key still fails this.
    m = re.search(r"for key in \(([^)]*)\):", REPO_SRC)
    assert m, "the JSONB decode loop is gone from the repo — every JSONB column now returns `str`"
    decoded = {k.strip().strip('"').strip("'") for k in m.group(1).split(",") if k.strip()}
    for column in ("checkpoint_state", "pass_state", "genre_tags"):
        assert column in decoded, f"{column} is selected but never JSON-decoded → silently defaults"


def test_the_model_carries_both_new_columns():
    r = PlanRun(
        id="00000000-0000-4000-8000-000000000001",
        created_by="00000000-0000-4000-8000-000000000002",
        book_id="00000000-0000-4000-8000-000000000003",
        mode="llm",
        genre_tags=["xianxia"],
        pass_state={},
    )
    assert r.genre_tags == ["xianxia"]
    assert r.pass_state == {}


import pytest


@pytest.mark.asyncio
async def test_the_run_detail_reports_the_SAME_pass_cursor_as_the_passes_endpoint():
    """BE-21: the run detail's derived pass view must AGREE with the /passes endpoint.

    Both derive freshness against the planning package, which the 5 package-reading passes count
    among their inputs. If `_serialize_run` omits the package id, `motifs`/`cast` (no pass deps)
    fingerprint against "" → fresh-forever → the detail's pass_cursor diverges from /passes even
    after a re-compile with a new package. This pins that the two producers of the same truth
    agree. The old source-text pin here asserted `**derive_view(run)` — i.e. the BUG.
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from app.services.plan_pass_service import PACKAGE_KIND, fingerprint

    user, book, pkg = uuid4(), uuid4(), uuid4()
    # `motifs` is PASS_ORDER[0]: no pass deps, reads_package ⇒ its only fingerprint input is the
    # package pointer. Record its fingerprint exactly as the worker does — WITH the package id.
    motifs_fp = fingerprint(input_artifact_ids=[str(pkg)], params={})
    run = PlanRun(
        id=uuid4(), created_by=user, book_id=book, mode="llm", status="proposed",
        active_job_id=None, genre_tags=["xianxia"],
        pass_state={
            "motifs": {
                "status": "completed", "decision": "auto",
                "artifact_id": str(uuid4()), "params": {}, "input_fingerprint": motifs_fp,
            },
        },
    )

    runs = AsyncMock()
    runs.get_for_book.return_value = run
    # LIST-NPLUS1: the package pointer rides the artifact-refs list `_serialize_run` already reads
    # (DISTINCT ON (kind) = latest per kind) — no extra query.
    runs.list_artifact_refs.return_value = [{"kind": PACKAGE_KIND, "artifact_id": str(pkg)}]

    async def _latest(book_id, run_id, kind):
        # `pass_status` resolves the package via latest_artifact; spec/preflight are absent here.
        return SimpleNamespace(id=pkg) if kind == PACKAGE_KIND else None

    runs.latest_artifact.side_effect = _latest
    svc = PlanForgeService(runs, AsyncMock(), AsyncMock(), llm=AsyncMock())

    detail = await svc.get_run_detail(user, book, run.id)
    passes = await svc.pass_status(user, book, run.id)

    assert passes["pass_cursor"] == 1                       # /passes: right by construction
    assert detail["pass_cursor"] == passes["pass_cursor"]   # …and the detail must AGREE
    assert {p["pass_id"]: p["fresh"] for p in detail["passes"]}["motifs"] is True
    assert detail["genre_tags"] == ["xianxia"]              # PF-15 round-trip, behaviourally
    assert "source_markdown" in detail                     # BE-3b — reopening a run can resume the braindump


# ── it is a RUN input, not platform config (Settings & Configuration Boundary) ──


def test_genre_is_not_an_env_flag():
    """"Would two users want different values?" — yes, obviously: two authors planning two books.
    So it is a per-run choice that rides the row, never a global `*_GENRE` env var."""
    from app import config

    cfg_src = Path(inspect.getfile(config)).read_text(encoding="utf-8")
    assert "genre" not in cfg_src.lower()
