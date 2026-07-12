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
    assert 'for key in ("checkpoint_state", "pass_state", "genre_tags")' in REPO_SRC


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


def test_the_serialized_run_RETURNS_genre_tags_and_the_derived_pass_view():
    """The response must round-trip what the caller asked for (else a client cannot tell a stored
    value from a dropped one), and it must carry the DERIVED pass view — PF-3 says fresh/cursor/
    blocked_at are computed at serialization and never stored."""
    src = Path(inspect.getfile(PlanForgeService)).read_text(encoding="utf-8")
    assert '"genre_tags": run.genre_tags' in src
    assert "**derive_view(run)" in src


# ── it is a RUN input, not platform config (Settings & Configuration Boundary) ──


def test_genre_is_not_an_env_flag():
    """"Would two users want different values?" — yes, obviously: two authors planning two books.
    So it is a per-run choice that rides the row, never a global `*_GENRE` env var."""
    from app import config

    cfg_src = Path(inspect.getfile(config)).read_text(encoding="utf-8")
    assert "genre" not in cfg_src.lower()
