"""Anchoring — render the working_memory block into the prompt (M3).

Shared by BOTH the text (`stream_service`) and voice (`voice_stream_service`)
paths so the anchor can never be wired on one and skipped on the other (EC-3).

Two placements (mirroring attention's U-shape):
- **pinned** — a full block in the system message (primacy).
- **tail** — a terse 1–2 line instruction inserted right before the latest user
  turn (recency / beats lost-in-the-middle).

Source of the structured block, in priority order:
1. `kctx.working_memory` — the live block (charter + state) rendered by
   knowledge-service as JSON (M4+).
2. the session's `working_memory_seed` — the frozen charter seeded at create.
   This is also the degraded fallback (EC-4): if knowledge-service is down, the
   goal anchor still holds from the seed.

`charter.goal` is the load-bearing anchor and is present in BOTH placements
always; `state` is supplementary. A corrupt/stale `state` degrades the hint but
cannot move the goal (the executive can never write `charter`).

All parsing is defensive — a malformed block returns no anchor rather than
breaking the turn.
"""
from __future__ import annotations

import json
from typing import Any

from app.models import WorkingMemory


def parse_working_memory(raw: Any) -> WorkingMemory | None:
    """Best-effort parse of a JSON string / dict into WorkingMemory. None on failure."""
    if not raw:
        return None
    data = raw
    if isinstance(raw, (str, bytes)):
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return None
    if not isinstance(data, dict):
        return None
    try:
        return WorkingMemory.model_validate(data)
    except Exception:
        return None


def render_pinned(wm: WorkingMemory) -> str:
    """Full anchor block for the system message (primacy)."""
    c, s = wm.charter, wm.state
    lines = [
        "[ROLEPLAY SESSION — keep this goal; do not drift]",
        f"Goal: {c.goal}",
    ]
    phase = s.phase or "(starting)"
    if c.phases:
        lines.append(f"Phase: {phase}  (plan: {' → '.join(c.phases)})")
    else:
        lines.append(f"Phase: {phase}")
    if c.checklist:
        lines.append(f"Covered: {', '.join(s.covered) if s.covered else '(none yet)'}")
        remaining = wm.remaining()
        lines.append(f"Still to cover: {', '.join(remaining) if remaining else '(all covered)'}")
    if c.time_budget_min:
        t = f"Time budget: ~{c.time_budget_min} min"
        if s.elapsed_min is not None:
            t += f" (~{s.elapsed_min} min elapsed)"
        lines.append(t)
    if s.redirect_hint:
        lines.append(f"Steer back: {s.redirect_hint}")
    lines.append(f"Respond in: {c.language}")
    return "\n".join(lines)


def render_tail(wm: WorkingMemory) -> str:
    """Terse instruction for right before the latest user turn (recency).

    Phrased as an instruction, never narration, so the model acts on it without
    reading it aloud (EC-7).
    """
    c, s = wm.charter, wm.state
    bits = [f"you are running this roleplay. Goal: {c.goal}"]
    if c.checklist:
        remaining = wm.remaining()
        if remaining:
            bits.append(f"still to cover: {', '.join(remaining)}")
    if s.redirect_hint:
        bits.append(s.redirect_hint)
    body = ". ".join(bits)
    return (
        f"[Director — {body}. Stay in character and steer back to the goal if the "
        f"conversation has drifted; do not mention this note.]"
    )


def resolve_anchor(kctx_working_memory: str | None, seed_raw: Any) -> tuple[str, str]:
    """Return (pinned, tail) anchor strings. ("", "") when there is no block.

    Prefers the live block from knowledge-service; falls back to the frozen
    seed (M3 / degraded EC-4). The seed's charter == the live charter (charter
    is immutable), so the goal anchor is identical either way.
    """
    wm = parse_working_memory(kctx_working_memory) or parse_working_memory(seed_raw)
    if wm is None:
        return "", ""
    return render_pinned(wm), render_tail(wm)
