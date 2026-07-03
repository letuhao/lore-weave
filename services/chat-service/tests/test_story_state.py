"""T4 — story_state distill / cadence / render (pure logic, effect-proving)."""

from app.services.story_state import (
    DEFAULT_CADENCE_TURNS,
    STORY_STATE_TOKEN_CAP,
    distill_story_state,
    render_story_state_block,
    should_refresh,
    source_hash,
)
from app.services.token_budget import estimate_tokens


class TestDistill:
    def test_empty_source_is_empty(self):
        assert distill_story_state("") == ("", 0)
        assert distill_story_state("   \n  ") == ("", 0)

    def test_small_source_kept_verbatim(self):
        src = "Lâm Uyển — the betrayed heiress.\nĐại Việt is the setting."
        value, est = distill_story_state(src)
        assert value == src.strip()
        assert est == estimate_tokens(src.strip())

    def test_large_source_truncated_under_cap_on_line_boundary(self):
        # 400 distinct lines, each a small fact → far over the cap.
        src = "\n".join(f"Fact {i}: something happens to entity number {i} here." for i in range(400))
        value, est = distill_story_state(src)
        assert est <= STORY_STATE_TOKEN_CAP
        # kept whole lines from the head (no mid-line cut)
        assert value.startswith("Fact 0:")
        assert "\n" in value
        assert all(line in src for line in value.splitlines())

    def test_single_over_cap_line_hard_truncates(self):
        src = "x" * 100_000  # one enormous line, no newline
        value, est = distill_story_state(src)
        assert value  # not empty
        assert est <= STORY_STATE_TOKEN_CAP * 2  # bounded (char fallback is generous)


class TestSourceHash:
    def test_stable_and_sensitive(self):
        assert source_hash("abc") == source_hash("abc")
        assert source_hash("abc") != source_hash("abd")
        assert source_hash("") == source_hash("")


class TestShouldRefresh:
    def test_no_cache_refreshes(self):
        assert should_refresh(cached_turn=None, current_turn=1, cached_hash=None, new_hash="h")

    def test_hash_change_refreshes(self):
        assert should_refresh(cached_turn=3, current_turn=4, cached_hash="a", new_hash="b")

    def test_lore_gate_refreshes(self):
        assert should_refresh(cached_turn=3, current_turn=4, cached_hash="a", new_hash="a", lore_gate=True)

    def test_scene_change_refreshes(self):
        assert should_refresh(cached_turn=3, current_turn=4, cached_hash="a", new_hash="a", scene_change=True)

    def test_cadence_elapsed_refreshes(self):
        assert should_refresh(
            cached_turn=0, current_turn=DEFAULT_CADENCE_TURNS, cached_hash="a", new_hash="a")

    def test_within_cadence_uses_cache(self):
        assert not should_refresh(cached_turn=3, current_turn=4, cached_hash="a", new_hash="a")


class TestRender:
    def test_wraps_nonempty(self):
        out = render_story_state_block("entities: A, B")
        assert out == "<story_state>\nentities: A, B\n</story_state>"

    def test_empty_is_empty_string(self):
        assert render_story_state_block("") == ""
        assert render_story_state_block("   ") == ""
