"""Error-block model + repo invariants (atom-edit Phase D, D3a).

These are the guards that do NOT need a database. The schema-level guarantees (the target/span/
kind CHECKs, the dedup partial index, and book_id derivation from composition_work) were proven
directly against Postgres — see the D3a evidence block in
docs/specs/2026-07-26-atom-edit/CHECKLIST.md.

What is pinned here is the layer above: that the closed sets are actually closed, and that the
repo's partial-update surface cannot be talked into moving a block's span or its status. Both
matter because an error block's whole value is that it points at a specific piece of prose — a
span that can drift under a PATCH is a block that silently starts describing the wrong sentence.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.db.models import ErrorBlock
from app.db.repositories import VersionMismatchError
from app.db.repositories.error_blocks import OPEN_STATUSES, ErrorBlocksRepo


def _payload(**over):
    base = dict(
        id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        project_id=uuid.uuid4(),
        book_id=uuid.uuid4(),
        target_kind="chapter_draft",
        chapter_id=uuid.uuid4(),
        start_offset=10,
        end_offset=25,
        quote="Nàng gật đầu.",
        source_fingerprint="sha256:abc",
        kind="continuity",
        note="she died in ch3",
    )
    base.update(over)
    return base


class TestErrorBlockModel:
    def test_a_well_formed_block_validates_and_defaults_to_open_human(self):
        block = ErrorBlock.model_validate(_payload())
        assert block.status == "open"
        assert block.source == "human"
        assert block.is_archived is False
        assert block.version == 1

    @pytest.mark.parametrize(
        "field,bad",
        [
            ("kind", "totally-made-up"),
            ("status", "in_progress"),
            ("source", "robot"),
            ("target_kind", "scene_draft"),
        ],
    )
    def test_every_closed_set_rejects_an_unenumerated_value(self, field, bad):
        """A free string here is the silent-no-op class the Frontend-Tool-Contract forbids: an
        un-enumerated `kind` would store fine and then match no branch downstream."""
        with pytest.raises(ValidationError):
            ErrorBlock.model_validate(_payload(**{field: bad}))

    def test_the_draft_job_arm_carries_a_job_and_no_chapter(self):
        block = ErrorBlock.model_validate(
            _payload(target_kind="draft_job", chapter_id=None, job_id=uuid.uuid4())
        )
        assert block.chapter_id is None
        assert block.job_id is not None


class TestUpdateSurface:
    """`update` is a FINDING editor, not a span editor."""

    @pytest.fixture
    def repo(self):
        return ErrorBlocksRepo(None)  # the guard raises before the pool is ever touched

    @pytest.mark.parametrize(
        "field",
        ["start_offset", "end_offset", "quote", "source_fingerprint", "chapter_id", "book_id"],
    )
    async def test_the_span_and_its_scope_are_NOT_patchable(self, repo, field):
        """Letting a PATCH move `start_offset` without also moving `quote` and the fingerprint
        would split the anchor triple apart — the block would still look valid while pointing at
        different prose. Re-marking is a new block; re-anchoring goes through `reanchor`."""
        with pytest.raises(ValueError, match="not updatable"):
            await repo.update(uuid.uuid4(), uuid.uuid4(), {field: 1})

    async def test_status_is_NOT_patchable(self, repo):
        """Status moves only through the lifecycle helpers, so a block can never be parked in a
        state no transition produced (e.g. 'resolved' with no proposal and no resolution)."""
        with pytest.raises(ValueError, match="not updatable"):
            await repo.update(uuid.uuid4(), uuid.uuid4(), {"status": "resolved"})

    @pytest.mark.parametrize("field", ["kind", "note", "desired"])
    async def test_the_finding_text_IS_patchable(self, repo, field):
        """Reaching the pool means the guard let it through — a TypeError from `None.acquire()`
        is the signal, and it proves the field was accepted rather than rejected."""
        with pytest.raises((AttributeError, TypeError)):
            await repo.update(uuid.uuid4(), uuid.uuid4(), {field: "x"})


def test_version_mismatch_carries_the_ROW_not_a_message():
    """The shared `VersionMismatchError` takes the CURRENT ROW, which the router returns in the
    412 body so a caller can re-base without another round-trip.

    Written after shipping exactly this bug in the first draft of the repo: a message string was
    passed instead. It constructs fine — one positional arg either way — and only fails later, at
    `exc.current.model_dump()`, turning a legitimate 412 into a 500. Same shape as the E1 bug in
    the engine: reusing a shared primitive without reading its contract.
    """
    block = ErrorBlock.model_validate(_payload(version=4))
    exc = VersionMismatchError(block)
    assert exc.current is block
    assert exc.current.model_dump(mode="json")["version"] == 4   # what the router actually calls


def test_orphaned_counts_as_still_wanting_attention():
    """An orphaned block is one whose prose moved out from under it. It is NOT resolved — the
    author still has to say whether they fixed it or not — so it must keep showing up in the
    open count, otherwise a lost mark reads exactly like a completed one."""
    assert "orphaned" in OPEN_STATUSES
    assert "resolved" not in OPEN_STATUSES
    assert "dismissed" not in OPEN_STATUSES
