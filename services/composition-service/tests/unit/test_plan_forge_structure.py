"""D-PLANFORGE-BEATS-UNWIRED — the tests that would have caught the flat-arc bug.

The defect: `package["beats"]` was never populated, so `beat_keys` was always empty, so
`parse_chapter_map` rejected EVERY beat_role the model returned and `unmapped_beats` could never be
non-empty. Ten chapters came out `beat_role=NULL` with a flat 50→72 tension ramp — no climax, no
resolution — and the blocking checkpoint reported perfect health.

Nothing caught it because every existing test asserted a shape rather than an EFFECT. So the
anchor test here (`test_empty_beat_keys_discards_every_role`) asserts the *failing mechanism*
directly: with no beats, a perfectly good model response is thrown away. That is the assertion
whose absence let this ship.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.engine.arc_plan import shape_tension_curve
from app.engine.plan import ChapterPlan, parse_chapter_map
from app.engine.plan_forge.structure import (
    DEFAULT_BUILTIN_NAME,
    resolve_structure,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ── fakes ────────────────────────────────────────────────────────────────────────────────────────

@dataclass
class FakeTemplate:
    id: UUID
    name: str
    kind: str
    beats: list[dict[str, Any]]
    owner_user_id: UUID | None = None


def _web_novel_beats() -> list[dict[str, Any]]:
    """The real seeded shape — `{key,label,order,purpose}` — not an invented one."""
    return [
        {"key": "hook", "label": "Hook", "order": 1, "purpose": "Open mid-tension."},
        {"key": "establishment", "label": "World", "order": 2, "purpose": "Stakes and goal."},
        {"key": "rising_conflict", "label": "Rising", "order": 3, "purpose": "Escalate."},
        {"key": "setback", "label": "Setback", "order": 4, "purpose": "A hard loss."},
        {"key": "climax", "label": "Climax", "order": 5, "purpose": "The payoff."},
        {"key": "resolution", "label": "Resolution", "order": 6, "purpose": "Bank the win."},
    ]


class FakeTemplatesRepo:
    def __init__(self, templates: list[FakeTemplate], *, raise_on: str | None = None) -> None:
        self._templates = templates
        self._raise_on = raise_on

    async def get(self, user_id: UUID, template_id: UUID) -> FakeTemplate | None:
        if self._raise_on == "get":
            raise RuntimeError("db down")
        return next((t for t in self._templates if t.id == template_id), None)

    async def list_for_user(
        self, user_id: UUID, *, include_archived: bool = False,
    ) -> list[FakeTemplate]:
        if self._raise_on == "list":
            raise RuntimeError("db down")
        return list(self._templates)


def _builtin_library() -> FakeTemplatesRepo:
    return FakeTemplatesRepo([
        FakeTemplate(uuid4(), DEFAULT_BUILTIN_NAME, "web_novel", _web_novel_beats()),
        FakeTemplate(uuid4(), "Three-Act (Generic)", "generic", [
            {"key": "setup", "order": 1, "purpose": "a"},
            {"key": "midpoint", "order": 2, "purpose": "b"},
            {"key": "climax", "order": 3, "purpose": "c"},
        ]),
    ])


# ── THE ANCHOR: the mechanism that silently ate the whole structural layer ───────────────────────

def test_empty_beat_keys_discards_every_role() -> None:
    """With no beats, a VALID model response is thrown away in full — this is the bug.

    The model answers correctly; `parse_chapter_map` still returns all-None because membership is
    checked against an empty set. This is what produced 10/10 NULL beat roles in production.
    """
    chapters = [ChapterPlan(chapter_id=f"e{i}", title=f"Ch{i}", sort_order=i, beat_role=None,
                            intent="") for i in range(1, 4)]
    good_response = (
        '{"chapters":[{"index":1,"beat":"hook","intent":"i1"},'
        '{"index":2,"beat":"climax","intent":"i2"},'
        '{"index":3,"beat":"resolution","intent":"i3"}],'
        '"unmapped_beats":["setback"]}'
    )

    mapped, unmapped = parse_chapter_map(good_response, chapters, beat_keys=set())
    assert [c.beat_role for c in mapped] == [None, None, None], "the pre-fix failure mode"
    assert unmapped == [], "unmapped_beats cannot fire either — the checkpoint looks healthy"

    # …and the downstream consequence: one None-run ⇒ a flat neutral ramp, no climax peak.
    flat = [c.tension_target for c in shape_tension_curve([c.beat_role for c in mapped])]
    assert max(flat) < 88, "no chapter can ever reach the climax band"

    # With the beats actually wired, the SAME response now lands.
    keys = {b["key"] for b in _web_novel_beats()}
    mapped2, unmapped2 = parse_chapter_map(good_response, chapters, beat_keys=keys)
    assert [c.beat_role for c in mapped2] == ["hook", "climax", "resolution"]
    assert unmapped2 == ["setback"]

    shaped = shape_tension_curve([c.beat_role for c in mapped2])
    assert max(t.tension_target for t in shaped) >= 88, "the climax must reach the climax band"
    assert shaped[-1].tension_target < shaped[1].tension_target, "the resolution must DROP"


# ── resolution ───────────────────────────────────────────────────────────────────────────────────

async def test_resolves_the_authors_explicit_choice() -> None:
    chosen = FakeTemplate(uuid4(), "Hero's Journey", "hero_journey", _web_novel_beats())
    repo = FakeTemplatesRepo([chosen])

    got = await resolve_structure(repo, uuid4(), structure_template_id=chosen.id)

    assert got.source == "run"
    assert got.name == "Hero's Journey"
    assert [b["key"] for b in got.beats] == [b["key"] for b in _web_novel_beats()]
    assert got.note == "", "an honoured choice needs no explanation"


async def test_no_choice_uses_the_named_default_and_SAYS_so() -> None:
    got = await resolve_structure(_builtin_library(), uuid4(), structure_template_id=None)

    assert got.source == "default"
    assert got.name == DEFAULT_BUILTIN_NAME
    assert got.beats, "a default that resolves to nothing is the original bug"
    # The whole point of `source`/`note`: a defaulted structure must never be indistinguishable
    # from one the author picked.
    assert "default" in got.note


async def test_missing_template_falls_back_but_reports_it() -> None:
    got = await resolve_structure(_builtin_library(), uuid4(), structure_template_id=uuid4())

    assert got.source == "default"
    assert got.beats
    assert "not found" in got.note


async def test_chosen_but_empty_template_does_not_silently_become_the_default() -> None:
    empty = FakeTemplate(uuid4(), "My Empty", "generic", [])
    repo = FakeTemplatesRepo([
        empty, FakeTemplate(uuid4(), DEFAULT_BUILTIN_NAME, "web_novel", _web_novel_beats()),
    ])

    got = await resolve_structure(repo, uuid4(), structure_template_id=empty.id)

    assert got.beats, "still usable"
    assert "My Empty" in got.note, "the author must learn their pick was overridden"


async def test_unreadable_library_is_absent_with_a_note_never_a_silent_empty() -> None:
    got = await resolve_structure(
        FakeTemplatesRepo([], raise_on="list"), uuid4(), structure_template_id=None,
    )

    assert got.beats == []
    assert got.source == "unavailable"
    assert "NO story structure" in got.note, "a structureless plan must announce itself"


async def test_unseeded_library_is_reported_not_defaulted() -> None:
    got = await resolve_structure(FakeTemplatesRepo([]), uuid4(), structure_template_id=None)

    assert got.source == "unavailable"
    assert "unseeded" in got.note


async def test_beats_are_ordered_and_keyless_rows_dropped() -> None:
    """Order matters — the L1 prompt renders "STRUCTURE BEATS (in order)" and the model assigns by
    position. A keyless row can never survive the membership check, so carrying it would only
    inflate `unmapped_beats` with a beat no chapter could have received."""
    scrambled = FakeTemplate(uuid4(), "Scrambled", "generic", [
        {"key": "climax", "order": 3, "purpose": "c"},
        {"key": "", "order": 2, "purpose": "keyless — must be dropped"},
        {"key": "hook", "order": 1, "purpose": "a"},
        {"not_a_key": "x", "order": 4},
    ])
    repo = FakeTemplatesRepo([scrambled])

    got = await resolve_structure(repo, uuid4(), structure_template_id=scrambled.id)

    assert [b["key"] for b in got.beats] == ["hook", "climax"]


async def test_provenance_block_is_always_emitted() -> None:
    """`package["structure"]` is written even on total failure — a consumer must always be able to
    tell WHY a plan has the shape it has."""
    got = await resolve_structure(
        FakeTemplatesRepo([], raise_on="list"), uuid4(), structure_template_id=None,
    )
    block = got.to_package()

    assert set(block) == {"template_id", "name", "kind", "source", "beat_count", "note",
                          "unshaped_beat_keys", "shapeable"}
    assert block["beat_count"] == 0
    assert block["source"] == "unavailable"
    assert block["note"]
    assert block["shapeable"] is False


async def test_every_builtin_vocabulary_is_shapeable() -> None:
    """Each seeded structure must be fully known to `shape_tension_curve`.

    Four of the six built-ins originally had ZERO keys in `_BANDS`, so picking Hero's Journey or
    Kishōtenketsu assigned beat roles and STILL produced a flat curve. That is the same defect
    wearing a different hat, and this is the test that stops it coming back.
    """
    from app.engine.arc_plan import known_beat_keys

    vocabularies = {
        "Web Novel Arc": ["hook", "establishment", "rising_conflict", "setback", "climax",
                          "resolution"],
        "Three-Act (Generic)": ["setup", "confrontation", "resolution"],
        "Hero's Journey": ["ordinary_world", "call_to_adventure", "refusal_of_the_call",
                           "meeting_the_mentor", "crossing_the_threshold", "tests_allies_enemies",
                           "approach", "ordeal", "reward", "the_road_back", "resurrection",
                           "return_with_elixir"],
        "Save the Cat": ["opening_image", "theme_stated", "setup", "catalyst", "debate",
                         "break_into_two", "b_story", "fun_and_games", "midpoint",
                         "bad_guys_close_in", "all_is_lost", "dark_night", "break_into_three",
                         "finale", "final_image"],
        "Story Circle": ["you", "need", "go", "search", "find", "take", "return", "change"],
        "Kishōtenketsu": ["ki", "sho", "ten", "ketsu"],
    }
    known = known_beat_keys()
    for name, keys in vocabularies.items():
        missing = [k for k in keys if k not in known]
        assert not missing, f"{name} has unshapeable beats: {missing}"


def test_every_builtin_vocabulary_produces_a_real_arc_shape() -> None:
    """Shapeable is not enough — each vocabulary must actually PEAK and then COME DOWN.

    A monotonic ramp (what the flat-curve bug produced) would pass a "no unknown keys" check while
    still giving the drafter no climax to aim at.
    """
    peaks = {
        "Hero's Journey": ["ordinary_world", "call_to_adventure", "tests_allies_enemies", "ordeal",
                           "resurrection", "return_with_elixir"],
        "Save the Cat": ["opening_image", "catalyst", "fun_and_games", "all_is_lost", "finale",
                         "final_image"],
        "Story Circle": ["you", "need", "search", "take", "return", "change"],
        "Kishōtenketsu": ["ki", "sho", "ten", "ketsu"],
        "Web Novel Arc": ["hook", "establishment", "rising_conflict", "setback", "climax",
                          "resolution"],
    }
    for name, roles in peaks.items():
        curve = [c.tension_target for c in shape_tension_curve(roles)]
        assert max(curve) >= 88, f"{name} never reaches a climax band: {curve}"
        assert curve[-1] < max(curve) - 20, f"{name} never comes back down: {curve}"
