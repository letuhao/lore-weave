"""V1 Phase A3 — adaptive diverge-K (spec D3).

K (the number of candidate drafts the auto path generates per scene) is derived
from the scene's **structural weight**, not a flat config: climax / midpoint /
crisis beats earn the full ceiling; connective / transition scenes get K=1 (the
V0 single-draft loop, free). No new model — the signal is the scene's
``tension`` (primary) + its ``beat_role`` (the structure beat key, secondary).
Clamped to ``[1, k_ceiling]`` where ``k_ceiling = compose_diverge_k``.

``tension`` is the EXISTING **0..100** scale (``outline_node.tension``; the
reasoning policy gates "high dramatic tension" at ``>=70``) — NOT 1-5. ``high_threshold``
defaults to 70 to match. The mid band is ``[high_threshold//2, high_threshold)``.

Fallback: a node with NEITHER ``beat_role`` NOR ``tension`` (hand-authored or
pre-A3 outline) → ``k_ceiling`` — i.e. the exact fixed-K behaviour A1 shipped, so
existing outlines see no regression.
"""

from __future__ import annotations

# Closed set of structure-beat keys that mark a high-tension TURN (climax /
# midpoint / crisis / reversal) across the 6 built-in templates (migrate.py
# BUILTIN_TEMPLATES beat `key`s). A scene whose beat_role is in this set is
# bumped one candidate above what its tension alone would earn. Unknown keys
# contribute nothing (no guess — the no-silent-inference rule).
HIGH_WEIGHT_BEATS: frozenset[str] = frozenset({
    # save_the_cat
    "catalyst", "midpoint", "all_is_lost", "dark_night", "break_into_three", "finale",
    # hero_journey
    "ordeal", "reward", "resurrection", "the_road_back",
    # story_circle
    "take",
    # kishotenketsu
    "ten",
    # web_novel
    "setback", "climax",
    # generic three-act + common synonyms
    "confrontation", "crisis",
})


# ── Motif tension reconcile (W2 / audit R3) ────────────────────────────
#
# Two tension scales coexist: the MOTIF library uses a coarse 1..5 authoring dial
# (motif.tension_target + motif.beats[].tension_target), while the OUTLINE/scene
# layer + this adaptive_k gate use the 0..100 scale (high gate at high_threshold,
# default 70). A bound motif beat carrying tension_target=4 must NOT be fed to
# adaptive_k as `4` (that reads as "calm", base=1) — it is mapped to 0..100 FIRST.
#
# This map is the SINGLE source of truth for the 1..5 → 0..100 conversion; nothing
# else hand-rolls it. Anchored so band semantics line up with adaptive_k's gates:
#   5 → 90 (well above the 70 high gate → ceiling K),
#   4 → 75 (above 70 → ceiling K; a motif turn/climax beat earns ceiling),
#   3 → 50 (mid band [high//2, high)),
#   2 → 30 (below mid → K=1),
#   1 → 10 (calm → K=1).
_MOTIF_TENSION_MAP: dict[int, int] = {1: 10, 2: 30, 3: 50, 4: 75, 5: 90}


def motif_tension_to_scale(
    tens5: int | None, *, fallback: int | None = None,
) -> int | None:
    """Map a motif 1..5 tension to the outline 0..100 scale (W2/§3, audit R3).

    Returns None when NEITHER the beat tension nor the motif-level `fallback` is a
    real int → the scene then gets the A3 neutral default (50) downstream, exactly
    as a model-omitted tension does (parse_scenes). `fallback` is the motif-level
    tension_target (also 1..5). A bool is rejected (Python bool is an int subtype —
    `True`/`False` must never read as tension 1/0). Out-of-range ints are clamped
    into 1..5 before the lookup, so the map can never KeyError.
    """
    v = tens5 if isinstance(tens5, int) and not isinstance(tens5, bool) else fallback
    if not isinstance(v, int) or isinstance(v, bool):
        return None
    return _MOTIF_TENSION_MAP[max(1, min(5, v))]


def adaptive_k(
    beat_role: str | None,
    tension: int | None,
    *,
    k_ceiling: int,
    high_threshold: int = 70,
) -> int:
    """Candidate count for one scene. ``k_ceiling`` is the upper bound (config
    ``compose_diverge_k``); ``high_threshold`` is the tension (0..100 scale) at/above
    which a scene earns the full ceiling.

    - both signals absent → ``k_ceiling`` (no-regression fallback for hand-authored
      / pre-A3 nodes).
    - tension primary: ``>= high_threshold`` → ceiling; ``>= high_threshold//2``
      (mid band) → 2; below → 1. Absent tension → base 1 (lean on beat_role).
    - beat_role secondary: a ``HIGH_WEIGHT_BEATS`` key bumps the base by 1.
    - result clamped to ``[1, k_ceiling]``.
    """
    ceiling = max(1, k_ceiling)
    if beat_role is None and tension is None:
        return ceiling

    if tension is None:
        base = 1
    elif tension >= high_threshold:
        base = ceiling
    elif tension >= high_threshold // 2:
        base = 2
    else:
        base = 1

    if beat_role is not None and beat_role.strip().lower() in HIGH_WEIGHT_BEATS:
        base += 1

    return max(1, min(base, ceiling))
