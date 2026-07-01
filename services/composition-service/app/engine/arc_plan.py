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
    "hook": (45, 65),
    "setup": (30, 50),
    "establishment": (35, 58),
    "inciting_incident": (52, 70),
    "rising_action": (55, 82),
    "rising_conflict": (55, 82),
    "midpoint": (65, 82),
    "complications": (62, 86),
    "setback": (66, 90),
    "crisis": (78, 94),
    "climax": (88, 100),
    "falling_action": (40, 62),
    "resolution": (30, 52),
    "denouement": (25, 45),
}
_DEFAULT_BAND = (50, 72)


@dataclass
class ChapterTension:
    chapter_index: int          # 1-based, in story order
    beat_role: str | None
    tension_target: int         # 0..100 — the chapter's intended peak band


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
