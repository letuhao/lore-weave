"""T4 — story_state distill / cadence / render (pure logic, effect-proving)."""

from app.services.story_state import (
    TRUNCATED_MARKER,
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
        # D-CONTEXT-BLOCK-ANSWERS-A-FILTERED-QUERY (2026-08-14) — a truncated value now leads with
        # TRUNCATED_MARKER, so the renderer can warn on every later turn including replays from
        # cache. The property this test has always protected is unchanged and still asserted
        # below: whole lines, taken from the HEAD, no mid-line cut.
        assert value.startswith(TRUNCATED_MARKER)
        body = value[len(TRUNCATED_MARKER):].lstrip()
        assert body.startswith("Fact 0:")
        assert "\n" in body
        assert all(line in src for line in body.splitlines())

    def test_single_over_cap_line_hard_truncates(self):
        src = "x" * 100_000  # one enormous ASCII line, no newline
        value, est = distill_story_state(src)
        assert value  # not empty
        assert est <= STORY_STATE_TOKEN_CAP  # script-aware shrink honors the cap

    def test_single_over_cap_line_cjk_honors_cap(self):
        # MED-1 (T4 review): a fixed chars/token ratio blows the cap 2-3x for CJK.
        src = "万古神帝魔女逆天诸天神魔仙侠世界" * 300  # ~1 tok/char, one line, no newline
        value, est = distill_story_state(src)
        assert value
        assert est <= STORY_STATE_TOKEN_CAP  # NOT 2.6x over

    def test_single_over_cap_line_vietnamese_honors_cap(self):
        src = "Ma Nữ Nghịch Thiên tái sinh với ma công nghịch thiên " * 400  # dense VN, one line
        value, est = distill_story_state(src.replace("\n", " "))
        assert value
        assert est <= STORY_STATE_TOKEN_CAP


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

    def test_an_untruncated_block_carries_no_note(self):
        """The SCOPE note was tried here and reverted — see story_state.py. It stopped the model
        trusting the block and gave it nowhere to go, turning "3 suggested entries" into "you
        don't have any" on a queue of one. An under-count is the worse error: the queue is never
        opened. This asserts the revert, so the note cannot drift back in without the measurement
        being redone."""
        out = render_story_state_block("entities: A, B")
        assert "[SCOPE]" not in out
        assert out == "<story_state>\nentities: A, B\n</story_state>"

    def test_a_truncated_block_says_so_and_hides_the_marker(self):
        """The marker is machinery, not prose for the model — it must be consumed by the renderer
        and replaced with a sentence, or the model sees '[truncated]' and has to guess."""
        value, _ = distill_story_state(
            "\n".join(f"Fact {i}: a sentence about entity {i}." for i in range(400)))
        out = render_story_state_block(value)
        assert "TRUNCATED to fit" in out
        assert TRUNCATED_MARKER not in out
        assert "Never state a total" in out

    def test_empty_is_empty_string(self):
        assert render_story_state_block("") == ""
        assert render_story_state_block("   ") == ""
