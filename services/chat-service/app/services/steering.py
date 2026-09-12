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
from dataclasses import dataclass
import re

from app.services.token_budget import estimate_tokens, scale_by_window

logger = logging.getLogger(__name__)

__all__ = ["select_steering", "select_steering_ex", "SteeringTruncation",
           "render_steering_block", "STEERING_TOKEN_CAP"]

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


@dataclass(frozen=True)
class SteeringTruncation:
    """T12 — what the soft cap actually dropped from this turn.

    #223 raised ``STEERING_TOKEN_CAP`` 2000→8000 after a 2026-09-06 run found 5 of 8 rules being
    dropped from every turn — including a locked arc outline and the corruption mechanics, so the
    model was generating against a bible it could not see. That fixed the SIZE and explicitly
    deferred the DISCLOSURE: truncation still has no UI-visible indicator, so an author whose
    bible genuinely outgrows the cap silently loses rules and can discover it only by reading
    server logs.

    An author cannot debug their own novel from a container's stderr. This carries the facts up to
    the turn so the UI can say what happened — OUT-5, "never silently truncate: report the cap"."""

    dropped: int
    dropped_names: list[str]
    kept: int
    cap_tokens: int
    kept_tokens: int

    def as_dict(self) -> dict:
        return {
            "dropped": self.dropped,
            "dropped_names": self.dropped_names,
            "kept": self.kept,
            "cap_tokens": self.cap_tokens,
            "kept_tokens": self.kept_tokens,
        }


def select_steering(
    entries: list[dict],
    *,
    message: str,
    active_title: str | None = None,
    context_length: int | None = None,
) -> list[dict]:
    """List-only wrapper — kept so callers that genuinely cannot act on a truncation (and the
    existing tests) are unchanged. A caller that REPORTS to a human wants `select_steering_ex`."""
    selected, _truncation = select_steering_ex(
        entries, message=message, active_title=active_title, context_length=context_length,
    )
    return selected


def select_steering_ex(
    entries: list[dict],
    *,
    message: str,
    active_title: str | None = None,
    context_length: int | None = None,
) -> tuple[list[dict], SteeringTruncation | None]:
    """Select the entries that apply to this turn, ordered always →
    scene_match → manual/auto, soft-capped at STEERING_TOKEN_CAP (dropping
    from the tail so `always` survives longest). The cap scales up for a session
    model with a larger real context_length (None ⇒ the flat default).

    Returns ``(selected, truncation_or_None)``. The second element is what makes a drop
    reportable rather than log-only — see SteeringTruncation."""
    if not entries:
        return [], None
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
        return [], None

    # Soft token cap: drop from the tail (manual first) while over budget.
    total = sum(estimate_tokens(f"## {e['name']}\n{e['body']}") for e in selected)
    dropped_names: list[str] = []
    while len(selected) > 1 and total > cap:
        victim = selected.pop()
        total -= estimate_tokens(f"## {victim['name']}\n{victim['body']}")
        dropped_names.append(str(victim.get("name") or ""))
    dropped = len(dropped_names)
    if dropped or total > cap:
        logger.warning(
            "steering over the %d-token soft cap: dropped %d entr%s, ~%d tokens kept",
            cap, dropped, "y" if dropped == 1 else "ies", total,
        )
        # T12 — hand the caller the FACTS, not just a log line. #223 raised this cap but
        # explicitly deferred the real problem: an author whose bible genuinely outgrows it still
        # loses rules with no UI-visible indication, discoverable only by reading server logs —
        # which is how the 2026-09-06 run found it, after the dropped rules had already been
        # silently absent from every generation turn. OUT-5: never silently truncate, report it.
        return selected, SteeringTruncation(
            dropped=dropped,
            dropped_names=dropped_names,
            kept=len(selected),
            cap_tokens=cap,
            kept_tokens=total,
        )
    return selected, None


def render_steering_block(selected: list[dict]) -> str:
    """Render the selected entries as the single <steering> system part.
    Returns "" when nothing was selected (caller skips the part)."""
    if not selected:
        return ""
    chunks = [f"## {e['name']}\n{str(e['body']).strip()}" for e in selected]
    return "<steering>\n" + "\n\n".join(chunks) + "\n</steering>"
