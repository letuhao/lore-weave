"""LOOM T3.5 — style_directive() prose-style prompt mapping (pure, no DB)."""

from __future__ import annotations

from app.packer.profile import NEUTRAL, BookProfile, style_directive


def test_neutral_emits_nothing():
    assert style_directive(NEUTRAL) == ""


def test_mid_band_density_and_pace_emit_nothing():
    # an explicit 'balanced' (34-66) should not spend a token saying 'be normal'
    p = BookProfile(density_level=50, pace_level=50)
    assert style_directive(p) == ""


def test_low_density_is_lean():
    out = style_directive(BookProfile(density_level=10))
    assert "lean" in out.lower() and out.startswith(" ")


def test_high_density_is_lush():
    assert "lush" in style_directive(BookProfile(density_level=90)).lower()


def test_low_pace_is_slow():
    assert "slow" in style_directive(BookProfile(pace_level=5)).lower()


def test_high_pace_is_fast():
    assert "fast" in style_directive(BookProfile(pace_level=95)).lower()


def test_character_voices_render_names_and_tags():
    p = BookProfile(character_voices=(("Kael", ("terse", "no purple prose")),))
    out = style_directive(p)
    assert "Kael" in out and "terse" in out and "no purple prose" in out


def test_voice_with_empty_tags_is_skipped():
    # a character whose tag list is empty contributes no voice clause
    p = BookProfile(character_voices=(("Mira", ()),))
    assert style_directive(p) == ""


def test_combined_density_pace_voice():
    p = BookProfile(
        density_level=90, pace_level=5,
        character_voices=(("Kael", ("terse",)),),
    )
    out = style_directive(p).lower()
    assert "lush" in out and "slow" in out and "kael" in out
