"""RAID C1 (DR-C1) — pure selection/render tests for per-book steering.

select_steering is pure (no I/O): entries in, matching entries out, ordered
always → scene_match → manual/auto, soft-capped at ~2000 tokens dropping from
the tail (manual first — DR-C1 "manual < scene_match < always keeps").
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests")
os.environ.setdefault("MINIO_SECRET_KEY", "test-minio-secret")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-internal-token")

from app.services.steering import (  # noqa: E402
    STEERING_TOKEN_CAP,
    render_steering_block,
    select_steering,
)


def _e(name: str, mode: str = "always", body: str = "b", pattern: str | None = None) -> dict:
    return {
        "id": f"id-{name}",
        "name": name,
        "body": body,
        "inclusion_mode": mode,
        "match_pattern": pattern,
    }


class TestModes:
    def test_always_included_on_every_turn(self):
        out = select_steering([_e("tone")], message="anything at all", active_title=None)
        assert [e["name"] for e in out] == ["tone"]

    def test_manual_requires_hash_name_token(self):
        entries = [_e("combat", mode="manual")]
        assert select_steering(entries, message="describe the fight") == []
        assert [e["name"] for e in select_steering(entries, message="use #combat here")] == ["combat"]

    def test_manual_hash_name_is_case_insensitive(self):
        entries = [_e("Combat-Style", mode="manual")]
        out = select_steering(entries, message="apply #combat-style now")
        assert [e["name"] for e in out] == ["Combat-Style"]

    def test_manual_hash_is_a_token_not_substring(self):
        entries = [_e("tone", mode="manual")]
        # "#tones" is a different token; "x#tone" is not a token boundary.
        assert select_steering(entries, message="#tones") == []
        assert select_steering(entries, message="x#tone") == []
        # trailing punctuation still triggers
        assert len(select_steering(entries, message="use #tone.")) == 1

    def test_auto_v1_triggers_like_manual(self):
        """DR-C1 v1 honesty: `auto` is #name-triggered until model-pull ships."""
        entries = [_e("lore", mode="auto")]
        assert select_steering(entries, message="no trigger here") == []
        assert len(select_steering(entries, message="pull #lore please")) == 1

    def test_scene_match_substring_case_insensitive(self):
        entries = [_e("battle", mode="scene_match", pattern="Battle")]
        assert select_steering(entries, message="m", active_title="the great BATTLE of dawn")
        assert select_steering(entries, message="m", active_title="quiet morning") == []
        assert select_steering(entries, message="m", active_title=None) == []

    def test_scene_match_regex_specials_are_literal(self):
        """v1 treats regex-special chars literally — 'Ch. 1 (dawn)' must only
        match itself, and '.*' must not match everything."""
        entries = [_e("dawn", mode="scene_match", pattern="Ch. 1 (dawn)")]
        assert select_steering(entries, message="m", active_title="Ch. 1 (dawn) — start")
        assert select_steering(entries, message="m", active_title="ChX 1 dawn") == []
        wild = [_e("w", mode="scene_match", pattern=".*")]
        assert select_steering(wild, message="m", active_title="anything") == []

    def test_missing_pattern_never_matches(self):
        entries = [_e("s", mode="scene_match", pattern=None)]
        assert select_steering(entries, message="m", active_title="anything") == []

    def test_malformed_entries_dropped(self):
        entries = [
            "not-a-dict",
            {"name": None, "body": "x"},
            {"name": "ok", "body": ""},
            _e("good"),
        ]
        out = select_steering(entries, message="m")  # type: ignore[arg-type]
        assert [e["name"] for e in out] == ["good"]


class TestOrderingAndCap:
    def test_order_always_scene_manual(self):
        entries = [
            _e("m1", mode="manual"),
            _e("s1", mode="scene_match", pattern="tavern"),
            _e("a1"),
            _e("a2"),
        ]
        out = select_steering(entries, message="use #m1", active_title="The Tavern")
        assert [e["name"] for e in out] == ["a1", "a2", "s1", "m1"]

    def test_cap_drops_from_tail_manual_first(self):
        # Each body ≈ 1000 tokens of ASCII (4000 chars) → 3 entries ≈ 3000 > 2000.
        big = "word " * 800  # 4000 chars ≈ 1000 tokens
        entries = [
            _e("keep-always", body=big),
            _e("scene", mode="scene_match", pattern="t", body=big),
            _e("manual", mode="manual", body=big),
        ]
        out = select_steering(entries, message="#manual", active_title="t")
        names = [e["name"] for e in out]
        assert names[0] == "keep-always"
        assert "manual" not in names  # dropped first (tail)
        assert len(names) < 3

    def test_single_oversized_always_survives(self):
        """The cap never drops the LAST entry — one oversized always-rule still
        renders (logged), it is the author's explicit choice."""
        huge = "word " * (STEERING_TOKEN_CAP * 5)
        out = select_steering([_e("epic", body=huge)], message="m")
        assert [e["name"] for e in out] == ["epic"]


class TestRender:
    def test_render_block_shape(self):
        block = render_steering_block([_e("tone", body="Keep it wry."), _e("pov", body="Close third.")])
        assert block.startswith("<steering>\n")
        assert block.endswith("\n</steering>")
        assert "## tone\nKeep it wry." in block
        assert "## pov\nClose third." in block

    def test_render_empty_is_empty_string(self):
        assert render_steering_block([]) == ""
