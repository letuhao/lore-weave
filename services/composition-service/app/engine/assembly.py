"""Chapter-assembly mode resolution (LOOM chapter-assembly-modes, B1).

A Work chooses HOW a chapter's prose is assembled:

- ``per_scene`` (default) — the validated per-scene engine (A1 diverge→converge,
  A2 canon-check/reflect, A3 adaptive-K); a chapter-stitch pass (B3) merges the
  done scenes into one smooth chapter.
- ``chapter`` — generate the whole chapter in ONE pass from the decompose plan
  (the ``eval_a_fair`` winning config); B2 implements the path.

B1 is plumbing only: this module resolves the effective mode from (request
override → work setting → config default) and is the single source the engine /
stitch paths key on. The ``chapter`` path itself lands in B2 — until then the
router 501s on a resolved ``chapter`` mode rather than silently running per-scene.
"""

from __future__ import annotations

from typing import Literal

AssemblyMode = Literal["per_scene", "chapter"]

# The closed set of valid modes. Mirrored by the GenerateBody Literal (request
# override) and the WorkPatch settings validator (stored setting) so a bad value
# is rejected at the boundary, never silently coerced.
ASSEMBLY_MODES: tuple[AssemblyMode, ...] = ("per_scene", "chapter")


def resolve_assembly_mode(
    override: str | None,
    work_settings: dict | None,
    default: str,
) -> AssemblyMode:
    """Resolve the effective assembly mode.

    Precedence: per-request ``override`` → work ``settings.assembly_mode`` →
    config ``default``. Any candidate that is not a valid mode is skipped
    (defense-in-depth: PATCH already validates the stored value, but a legacy /
    hand-edited row must never crash generation). Falls back to ``per_scene``.
    """
    candidates = (override, (work_settings or {}).get("assembly_mode"), default)
    for candidate in candidates:
        if candidate in ASSEMBLY_MODES:
            return candidate  # type: ignore[return-value]
    return "per_scene"
