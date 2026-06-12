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
