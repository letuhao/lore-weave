"""S1 — gather_recent dual-source state-reinjection (D-COMP-LONGFORM-STATE-REINJECTION).

Primary source = the accepted chapter draft; fallback (no draft yet) = prior
generated scene winners, STRICTLY position-bounded. The SQL position-bound
(story_order < current) is live-smoke/integration; here we lock the gather logic:
draft-wins, fallback-fires-only-when-draft-empty, and the cutoff passed to the
repo is the current scene's story_order (so later scenes are excluded).
"""

from __future__ import annotations

import uuid

import pytest

from app.clients.book_client import BookClientError
from app.packer.lenses import gather_recent

USER = uuid.uuid4()
PROJECT = uuid.uuid4()
BOOK = uuid.uuid4()
CH = uuid.uuid4()


class _Book:
    def __init__(self, text):
        self._text = text
    async def get_draft(self, book_id, chapter_id, bearer):
        if self._text is None:
            raise BookClientError(502, "BOOK_SERVICE_UNAVAILABLE", "down")
        return {"text_content": self._text}


class _Jobs:
    def __init__(self, prior):
        self._prior = prior
        self.called_with = None
    async def prior_scene_drafts(self, project_id, chapter_id, before_story_order):
        self.called_with = before_story_order
        return list(self._prior)


async def test_draft_present_uses_draft_no_fallback():
    jobs = _Jobs(["SHOULD NOT APPEAR"])
    out = await gather_recent(_Book("a\nb\nc\nd"), BOOK, CH, "jwt", k=2,
                              jobs_repo=jobs, project_id=PROJECT, story_order=5)
    assert out == ["c", "d"]          # draft tail (last k)
    assert jobs.called_with is None   # fallback NOT invoked when a draft exists


async def test_draft_empty_falls_back_to_prior_generated_scenes():
    jobs = _Jobs(["scene one para1\nscene one para2", "scene two para1"])
    out = await gather_recent(_Book(""), BOOK, CH, "jwt",
                              jobs_repo=jobs, project_id=PROJECT, story_order=5)
    assert out == ["scene one para1", "scene one para2", "scene two para1"]
    assert jobs.called_with == 5      # cutoff = current story_order (later scenes excluded)


async def test_book_outage_then_fallback():
    jobs = _Jobs(["prior prose"])
    out = await gather_recent(_Book(None), BOOK, CH, "jwt",
                              jobs_repo=jobs, project_id=PROJECT, story_order=3)
    assert out == ["prior prose"] and jobs.called_with == 3


async def test_no_jobs_repo_and_empty_draft_returns_empty():
    out = await gather_recent(_Book(""), BOOK, CH, "jwt")  # no fallback wired
    assert out == []


async def test_fallback_skipped_when_story_order_none():
    # a node with no story_order can't be safely position-bounded → no fallback
    jobs = _Jobs(["prose"])
    out = await gather_recent(_Book(""), BOOK, CH, "jwt",
                              jobs_repo=jobs, project_id=PROJECT, story_order=None)
    assert out == [] and jobs.called_with is None
