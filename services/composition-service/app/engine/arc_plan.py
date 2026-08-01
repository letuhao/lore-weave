"""Planning pipeline · Stage 2 — `shape_tension_curve` (deliberate arc pacing).

The one-shot decompose set no tension intent, so the L2 model free-ran each chapter's
scenes and blew to 100 in CHAPTER 1 (the planning-review defect: the origin telescoped
and there was nowhere left to escalate). This step derives a DELIBERATE per-chapter
tension target from the arc structure — a rising curve that caps the opening, only
reaches 100 at the climax, and drops at the resolution — to be fed into the scene
decompose (Stage 4) so scenes aim for the band instead of maxing early.

Deterministic + pure (no LLM): the curve shape is STRUCTURAL (it follows the beats), so
it should be predictable and testable, not sampled. Beat roles map to a (base, peak)
band; a run of consecutive same-role chapters RAMPS base→peak so a multi-chapter beat
still rises within itself; an unmapped/None role falls back to a neutral mid band.
"""

from __future__ import annotations

from dataclasses import dataclass

# (base, peak) tension bands per beat role — a deliberate rising arc. 100 appears ONLY
# at the climax; the opening (hook/setup) is intentionally capped well below it; the
# resolution drops. Keys cover the common web-novel / story-circle / 3-act beat names.
_BANDS: dict[str, tuple[int, int]] = {
    # ── generic / web-novel vocabulary ──
    "hook": (45, 65),
    "setup": (30, 50),
    "establishment": (35, 58),
    "inciting_incident": (52, 70),
    "rising_action": (55, 82),
    "rising_conflict": (55, 82),
    "confrontation": (60, 85),       # Three-Act's middle
    "midpoint": (65, 82),
    "complications": (62, 86),
    "setback": (66, 90),
    "crisis": (78, 94),
    "climax": (88, 100),
    "falling_action": (40, 62),
    "resolution": (30, 52),
    "denouement": (25, 45),

    # D-PLANFORGE-BEATS-UNWIRED — the OTHER seeded structures' vocabularies.
    #
    # Only the web-novel/3-act keys were mapped, so four of the six built-in templates
    # (Hero's Journey, Save the Cat, Story Circle, Kishōtenketsu) had NO key in this dict — every
    # beat fell to `_DEFAULT_BAND` and the curve came out flat. That is a quieter re-run of the very
    # bug the beats wiring fixes: the roles would be assigned, and the SHAPE would still be a
    # straight line. A structure the planner cannot shape is a structure in name only.
    #
    # ── Hero's Journey ──
    "ordinary_world": (30, 50),
    "call_to_adventure": (52, 70),
    "refusal_of_the_call": (45, 62),
    "meeting_the_mentor": (40, 58),
    "crossing_the_threshold": (55, 72),
    "tests_allies_enemies": (55, 82),
    "approach": (62, 80),
    "ordeal": (78, 94),              # the central brush with death — a crisis, not yet the climax
    "reward": (50, 68),              # the deliberate exhale after the ordeal
    "the_road_back": (62, 84),
    "resurrection": (88, 100),       # THE climax of this vocabulary
    "return_with_elixir": (30, 52),

    # ── Save the Cat ──
    "opening_image": (30, 48),
    "theme_stated": (32, 50),
    "catalyst": (52, 70),
    "debate": (45, 62),
    "break_into_two": (55, 72),
    "b_story": (45, 62),
    "fun_and_games": (55, 78),
    "bad_guys_close_in": (66, 88),
    "all_is_lost": (72, 92),
    "dark_night": (70, 90),          # low EXTERNAL action, peak internal despair — keep it high
    "break_into_three": (68, 86),
    "finale": (88, 100),
    "final_image": (28, 48),

    # ── Story Circle ──
    "you": (30, 50),
    "need": (45, 64),
    "go": (55, 72),
    "search": (58, 80),
    "find": (70, 88),
    "take": (78, 94),                # "pay a heavy price" — the cost beat
    "return": (60, 82),
    "change": (32, 54),

    # ── Kishōtenketsu (no conflict spine; the TURN carries the energy) ──
    "ki": (30, 50),
    "sho": (45, 65),
    "ten": (78, 94),                 # the recontextualising twist — this vocabulary's peak
    "ketsu": (35, 55),
}
_DEFAULT_BAND = (50, 72)


@dataclass
class ChapterTension:
    chapter_index: int          # 1-based, in story order
    beat_role: str | None
    tension_target: int         # 0..100 — the chapter's intended peak band


def known_beat_keys() -> frozenset[str]:
    """The beat keys this module can actually SHAPE a curve from.

    Exported so a caller can warn when a structure's vocabulary is unknown to the shaper. Without
    it, an unrecognised key degrades to the neutral band silently — the curve looks computed but is
    flat, which is indistinguishable from the no-beats bug it replaced.
    """
    return frozenset(_BANDS)


def band_for(beat_role: str | None) -> tuple[int, int]:
    """The (base, peak) band for a beat role; the neutral mid band for None/unknown."""
    if not beat_role:
        return _DEFAULT_BAND
    return _BANDS.get(beat_role.strip().lower(), _DEFAULT_BAND)


def shape_tension_curve(beat_roles: list[str | None]) -> list[ChapterTension]:
    """A deliberate per-chapter tension target from the ordered beat roles. Consecutive
    same-role chapters ramp base→peak (a multi-chapter beat still rises); a single-chapter
    beat sits at its peak. Pure + deterministic — order in == order out, 1-based indices."""
    out: list[ChapterTension] = []
    i = 0
    n = len(beat_roles)
    while i < n:
        role = beat_roles[i]
        # extent of the run of identical roles (None groups with None)
        j = i
        while j < n and beat_roles[j] == role:
            j += 1
        run_len = j - i
        base, peak = band_for(role)
        for k in range(run_len):
            # ramp base→peak across the run; a length-1 run sits at the peak
            if run_len == 1:
                target = peak
            else:
                target = round(base + (peak - base) * k / (run_len - 1))
            out.append(ChapterTension(
                chapter_index=i + k + 1, beat_role=role, tension_target=int(target),
            ))
        i = j
    return out
