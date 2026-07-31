"""D-GENERATED-FACT-HAS-NO-HOME — the orchestration half: extract, merge, persist.

Kept apart from `engine/exit_state.py` on purpose. That module is pure — no repo, no LLM, no
network — which is what makes its rules (what counts as an identity, when an author's cast is
untouchable, how a row renders into a prompt) testable without a stack. This one is the wiring,
and it is the part that has to be degrade-safe.

**It can never fail a generate.** Every failure mode returns a reason string and the caller
carries on with the draft it already paid for. A continuity RECORD is worth less than the prose;
a write-back that could raise would be trading the valuable thing for the cheap one. That is the
same F1 rule the canon guard and the seam check already follow here.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.engine.cross_scene_check import _TAIL_CHARS, extract_people_from
from app.engine.exit_state import cast_rows_from_people, merge_generated_cast

logger = logging.getLogger(__name__)


async def record_scene_exit_state(
    pool, judge, *, user_id: str, outline_node_id: str | UUID | None,
    final_text: str, model_source: str, model_ref: str,
    source_language: str = "auto",
    people: list[dict[str, Any]] | None = None,
    trace_id: str | None = None,
    cancel_check=None,
) -> dict[str, Any]:
    # `pool=None` ⇒ resolve it here, INSIDE the guard below. `get_pool()` raises when the app
    # is not fully started, and the router's first version of this call did the resolution at
    # the call site — outside the try — so the "can never fail a generate" promise was false
    # on exactly the path that made it. Four router tests went red on it, which is the only
    # reason it is not in production. A degrade-safe helper must own every step that can throw,
    # including the one that gets it its dependencies.
    """Record who the finished scene left standing, into `outline_node.exit_state`.

    ``people`` lets a caller hand in an extraction it has ALREADY paid for — the seam check
    extracts the head of this very scene moments later, and paying twice for one passage would
    be the kind of quiet cost that only shows up on a bill. Absent, this extracts the scene's
    TAIL itself.

    Why the tail. `exit_state` is what the scene LEAVES, so the end of it is the honest span,
    and it is the exact span the seam check reads for the earlier side — the two agree by
    construction rather than by luck. The cost is real and is stated rather than hidden: a
    character who appears only in a scene's opening is not recorded.

    Returns `{"status", "cast_size"}` — always. `status` is one of `recorded` ·
    `author_owned` · `no_cast_extracted` · `no_node` · `degraded` · `write_failed`.
    """
    if not outline_node_id:
        # The chapter single-pass and the stitch path have no per-scene node to write to.
        # That is a real boundary, not an oversight, and the envelope says so rather than
        # letting a chapter-scoped generate look like a scene that recorded nothing.
        return {"status": "no_node", "cast_size": 0}
    if not (final_text or "").strip():
        return {"status": "no_cast_extracted", "cast_size": 0}

    try:
        if pool is None:
            from app.db.pool import get_pool
            pool = get_pool()
        if people is None:
            people = await extract_people_from(
                judge, user_id=user_id, model_source=model_source, model_ref=model_ref,
                text=final_text[-_TAIL_CHARS:], source_language=source_language,
                trace_id=trace_id, cancel_check=cancel_check,
            )
        if people is None:
            return {"status": "degraded", "cast_size": 0}

        cast = cast_rows_from_people(people)

        from app.db.repositories.outline import OutlineRepo
        repo = OutlineRepo(pool)
        node = await repo.get_node(UUID(str(outline_node_id)))
        if node is None:
            return {"status": "no_node", "cast_size": 0}

        envelope, reason = merge_generated_cast(node.exit_state, cast)
        if envelope is None:
            return {"status": reason, "cast_size": len(cast)}

        # No `expected_version`: this is a MAINTAINED field, not an authored edit, and a
        # 412 here would fail a write-back over an unrelated concurrent title change. The
        # thing it must not race is an author's cast, and that is guarded by provenance
        # above, not by the row version.
        await repo.update_node(UUID(str(outline_node_id)), {"exit_state": envelope})
        return {"status": "recorded", "cast_size": len(cast)}
    except Exception:  # noqa: BLE001 — F1: a record is never worth failing a generate for.
        logger.warning("exit-state write-back failed (advisory)", exc_info=True)
        return {"status": "write_failed", "cast_size": 0}
