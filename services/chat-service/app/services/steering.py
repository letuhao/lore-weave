"""RAID C1 (DR-C1) — per-book steering selection + rendering.

Pure functions (no I/O) so the selection contract is unit-testable in
isolation. stream_service fetches the enabled entries from book-service
(book_steering_client), selects the ones that match this turn, and renders
ONE ``<steering>`` system part right after the main system prompt.

Selection per DR-C1:
  always      — included on every book-scoped turn
  manual      — included when "#name" appears in the user message
                (case-insensitive token)
  auto        — v1 honesty: triggered like manual (#name only); the
                model-pull tool is a follow-up
  scene_match — included when match_pattern matches the active chapter/
                scene title (case-insensitive SUBSTRING; regex-special
                chars are treated literally in v1)

Order: always, then scene_match, then manual/auto. Soft cap ~STEERING_TOKEN_CAP tokens
(estimate_tokens): drop from the TAIL — manual first, then scene_match,
then always keeps (DR-C1 "manual < scene_match < always") — and log.
"""
from __future__ import annotations

import logging
import re

from app.services.token_budget import estimate_tokens, scale_by_window

logger = logging.getLogger(__name__)

__all__ = ["select_steering", "render_steering_block", "STEERING_TOKEN_CAP"]

# DR-C1 soft cap — steering is taxed every turn; keep tight relative to the window.
# Tuned around a mid-size (~200K) window; `scale_by_window` grows the cap for a caller
# that resolves the session model's real (larger) context_length, instead of every
# model being capped at the same flat number.
#
# Was 2000 until measured against a real per-book story bible (human-sim run,
# 2026-09-06): 8 solidly-written "always" rules (character baseline, corruption
# mechanics, a locked arc outline) totalled 4944 tokens, and the flat 2000 cap
# silently dropped 5 of them — including the locked arc outline and the corruption-
# tier mechanics, i.e. exactly the plot-critical content steering exists to protect —
# with no indication anywhere in the UI that this had happened. The Steering panel
# itself advertises up to 20 rules x 8000 chars (~40K tokens of storable content), so
# 2000 delivered under 5% of the advertised capacity. 8000 keeps steering to ~4% of a
# 200K window (still deliberately tight — it is taxed every turn) while covering a
# realistic multi-rule bible; `scale_by_window` still grows it further for genuinely
# larger context windows.
STEERING_TOKEN_CAP = 8000

# "#name" token extraction: word chars (unicode) + hyphen, so "#tone." and
# "(#combat-style)" trigger, but "x#tone" does not (a token, not a substring).
_HASH_TOKEN_RE = re.compile(r"(?<!\w)#([\w-]+)", re.UNICODE)


def _mentioned_names(message: str) -> set[str]:
    if not message:
        return set()
    return {m.casefold() for m in _HASH_TOKEN_RE.findall(message)}


def _title_matches(pattern: str | None, active_title: str | None) -> bool:
    """Case-insensitive plain-substring match (regex specials literal in v1)."""
    if not pattern or not active_title:
        return False
    return pattern.casefold() in active_title.casefold()


def select_steering(
    entries: list[dict],
    *,
    message: str,
    active_title: str | None = None,
    context_length: int | None = None,
) -> list[dict]:
    """Select the entries that apply to this turn, ordered always →
    scene_match → manual/auto, soft-capped at STEERING_TOKEN_CAP (dropping
    from the tail so `always` survives longest). The cap scales up for a session
    model with a larger real context_length (None ⇒ the flat default)."""
    if not entries:
        return []
    cap = scale_by_window(STEERING_TOKEN_CAP, context_length)
    mentioned = _mentioned_names(message)

    always: list[dict] = []
    scene: list[dict] = []
    manual: list[dict] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        name = e.get("name")
        body = e.get("body")
        if not isinstance(name, str) or not isinstance(body, str) or not body:
            continue
        mode = e.get("inclusion_mode") or "always"
        if mode == "always":
            always.append(e)
        elif mode == "scene_match":
            if _title_matches(e.get("match_pattern"), active_title):
                scene.append(e)
        elif mode in ("manual", "auto"):
            # `auto` v1: triggered like manual (#name) — model-pull is a follow-up.
            if name.casefold() in mentioned:
                manual.append(e)

    selected = always + scene + manual
    if not selected:
        return []

    # Soft token cap: drop from the tail (manual first) while over budget.
    total = sum(estimate_tokens(f"## {e['name']}\n{e['body']}") for e in selected)
    dropped = 0
    while len(selected) > 1 and total > cap:
        victim = selected.pop()
        total -= estimate_tokens(f"## {victim['name']}\n{victim['body']}")
        dropped += 1
    if dropped or total > cap:
        logger.warning(
            "steering over the %d-token soft cap: dropped %d entr%s, ~%d tokens kept",
            cap, dropped, "y" if dropped == 1 else "ies", total,
        )
    return selected


def render_steering_block(selected: list[dict]) -> str:
    """Render the selected entries as the single <steering> system part.
    Returns "" when nothing was selected (caller skips the part)."""
    if not selected:
        return ""
    chunks = [f"## {e['name']}\n{str(e['body']).strip()}" for e in selected]
    return "<steering>\n" + "\n\n".join(chunks) + "\n</steering>"
