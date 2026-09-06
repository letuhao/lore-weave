"""T4 (Context Budget Law) — story_state Core Memory Block: distill, cadence, render.

Pure logic (no I/O) so it is trivially testable. The `story_state` block is a
cached, bounded projection of the message-INDEPENDENT grounding gist (the L0 +
project summary/instructions "story bible" prefix that knowledge build_context
returns as `stable_context`). It exists so a turn whose expensive per-turn
grounding was gated (T5) still carries the load-bearing lore as a SAFETY NET
(sealed #1/#3, D4) — the follow-up "make it darker" never loses the entities the
rewrite needs.

sealed #3: `story_state` only, auto-projected, NO LLM and NO agent-write tool
(so distillation here is deterministic truncation, not summarization).
"""

from __future__ import annotations

import hashlib

from app.services.token_budget import estimate_tokens

STORY_STATE_LABEL = "story_state"

# Bound the block cost (T4 GATE: "block token cost ≤ ceiling"). ~1.2K tokens is a
# generous story-bible gist while staying a small fraction of any window.
STORY_STATE_TOKEN_CAP = 1200

#: Written INTO the distilled value when it had to be cut. Inside rather than beside, because the
#: value is what gets CACHED — a flag returned alongside it is right once and lost on every replay.
TRUNCATED_MARKER = "[truncated]"

# sealed #5 — refresh cadence in turns when nothing else triggers a refresh.
DEFAULT_CADENCE_TURNS = 5


def source_hash(stable_context: str) -> str:
    """Short stable hash of the grounding source — lets a refresh no-op when the
    story-bible prefix is byte-identical (skip a pointless write + version bump)."""
    return hashlib.sha256((stable_context or "").encode("utf-8")).hexdigest()[:16]


def distill_story_state(
    stable_context: str, *, token_cap: int = STORY_STATE_TOKEN_CAP
) -> tuple[str, int]:
    """Distill the message-independent grounding into the bounded block body.

    Deterministic (no LLM): take `stable_context` and, if it exceeds `token_cap`,
    truncate on a line boundary (keeping whole lines — the story-bible is
    line-structured: entities, facts, instructions). Returns (value, token_estimate).
    """
    text = (stable_context or "").strip()
    if not text:
        return "", 0
    est = estimate_tokens(text)
    if est <= token_cap:
        return text, est
    # 🔴 THE MARKER MUST COME OUT OF THE BUDGET, NOT ON TOP OF IT. Prepending it after shrinking
    # to `token_cap` pushed the block to 1203 tokens against a 1200 ceiling — and "block token
    # cost <= ceiling" is the T4 GATE this file exists under, so a truthfulness note that quietly
    # overspends the budget is just a different defect. Reserve its cost first; everything below
    # then shrinks into what is left.
    body_cap = max(1, token_cap - estimate_tokens(TRUNCATED_MARKER) - 1)
    # Everything past this point IS a truncation, and the marker rides INSIDE the returned value
    # rather than beside it: the value is what gets cached and re-rendered on later turns, so a
    # flag returned alongside would be correct once and then silently lost on every replay.
    # Truncate line-wise until under the cap (keep the head — L0/summary leads).
    kept: list[str] = []
    running = 0
    for line in text.splitlines():
        line_tok = estimate_tokens(line) + 1
        if running + line_tok > body_cap:
            break
        kept.append(line)
        running += line_tok
    joined = "\n".join(kept).strip()
    value = f"{TRUNCATED_MARKER}\n{joined}" if joined else ""
    if not joined:
        # A single over-cap line with no newline → shrink script-awarely. A fixed
        # chars/token ratio (e.g. *4) is 2-3x WRONG for CJK/VN (estimate_tokens
        # exists precisely because of that), so iterate against the real estimator
        # until under the cap — never assume 4 chars/token (MED-1, T4 review).
        value = text
        while value and estimate_tokens(value) > body_cap:
            ratio = body_cap / estimate_tokens(value)
            value = value[: max(1, int(len(value) * ratio))]
        # This branch cut a line mid-way, so it is a truncation too — marking only the
        # line-boundary path would leave the WORST case (a sentence stopped mid-word) as the one
        # the model is never warned about.
        value = f"{TRUNCATED_MARKER}\n{value.strip()}" if value.strip() else ""
    return value, estimate_tokens(value)


def should_refresh(
    *,
    cached_turn: int | None,
    current_turn: int,
    cached_hash: str | None,
    new_hash: str,
    lore_gate: bool = False,
    scene_change: bool = False,
    cadence: int = DEFAULT_CADENCE_TURNS,
) -> bool:
    """sealed #5 — refresh the cache when ANY of: no cache yet · the source content
    changed (hash differs) · an explicit lore-needed gate this turn · a scene/chapter
    change · `cadence` turns elapsed since the last refresh. Else project from cache."""
    if cached_turn is None or cached_hash is None:
        return True                      # nothing cached yet
    if new_hash != cached_hash:
        return True                      # the grounding source changed
    if lore_gate or scene_change:
        return True                      # an explicit trigger
    return (current_turn - cached_turn) >= cadence


#: 🔴 REVERTED 2026-08-14 — THIS WAS TRIED AND IT MADE THE ANSWER DIFFERENTLY WRONG.
#:
#: The block was being used to answer questions it cannot answer: on a fixture with three
#: entities and exactly ONE tagged 'ai-suggested', "Are there any suggested entries waiting for me
#: to review?" got "3 suggested entries waiting for your review". So the block was made to declare
#: its own scope — "a snapshot of the WHOLE bible, no filter applied; for a SUBSET call the tool".
#:
#: Measured after deploying it, same fixture, K=3: "No, you don't have any suggested entries
#: waiting for your review", 3 of 3. The model correctly stopped trusting the block — and then had
#: nowhere to go, because `glossary_list_ai_suggestions` is still surfaced on 0 of 3 runs. It fell
#: back to `glossary_search` and guessed the other way.
#:
#: An under-count is plausibly the WORSE of the two: "you have three waiting" sends the author to
#: look and find one, while "nothing is waiting" means the queue is never opened at all. Trading a
#: visible error for a silent one is not a fix, and the RUNBOOK is explicit that rewording a
#: message is not a fix without new evidence. The new evidence refused it.
#:
#: Kept here as a comment rather than deleted because the NEXT person to notice this defect will
#: reach for exactly this, and the measurement is the useful part. The real gap is underneath:
#: telling the model not to answer from the block is worth nothing until the tool that CAN answer
#: is reachable. See D-CONTEXT-BLOCK-ANSWERS-A-FILTERED-QUERY (open).
#:
#: _SCOPE_NOTE = "[SCOPE] A cached snapshot of the WHOLE story bible, with no filter applied. …"

_TRUNCATED_NOTE = (
    "[SCOPE] This snapshot was TRUNCATED to fit its budget — items are missing. Never state a "
    "total or say 'that is all' from it."
)


def render_story_state_block(value: str, *, truncated: bool = False) -> str:
    """The projected block text — wrapped so the model reads it as persistent session state.

    🔴 THE BLOCK MUST SAY WHAT IT IS NOT. Measured live 2026-08-14, K=3, on a fixture holding
    three glossary entities of which exactly ONE was tagged 'ai-suggested'. Asked "Are there any
    suggested entries waiting for me to review?", the model answered "3 suggested entries waiting
    for your review" — it read this block, which carries EVERY entity, and reported the total as
    the review queue. No tool was called, the store never changed, and every bar in the harness
    was green: a read that writes nothing can still be confidently wrong.

    That is the 2026-08-13 incident in mirror image ("you haven't declared any" over a populated
    table, versus "you have three waiting" over a queue of one), and the cause is the same shape:
    a surface that cannot answer the question given, answering it anyway. The block was doing its
    job — it is a SAFETY NET so a follow-up never loses the entities a rewrite needs — but it was
    presented as undifferentiated "state", so a filtered question landed on it.

    🔴 AND THE OBVIOUS FIX WAS TRIED HERE AND REVERTED. Making the block declare its own scope
    ("a snapshot of the WHOLE bible; for a SUBSET call the tool") was deployed and measured on the
    same fixture, K=3. The answer became "No, you don't have any suggested entries waiting for
    your review", 3 of 3 — on a queue of one. The model correctly stopped trusting the block and
    then had nowhere to go, because the tool that CAN answer is still surfaced on 0 of 3 runs; it
    fell back to glossary_search and guessed the other way.

    An under-count is the worse of the two: "three waiting" sends the author to look and find one,
    while "nothing waiting" means the queue is never opened. Trading a visible error for a silent
    one is not a fix. The full note is kept as a comment above _TRUNCATED_NOTE, with the
    measurement, so the next person to reach for it starts from the evidence.

    What survives is the TRUNCATION note, which is a statement about THIS TEXT — items are missing
    — and needs no other tool to exist before the model can act on it.

    🔴 PROSE IS NOT A FIX WITHOUT EVIDENCE (RUNBOOK), and here the evidence refused it.
    """
    v = (value or "").strip()
    if not v:
        return ""
    cut = truncated or v.startswith(TRUNCATED_MARKER)
    if v.startswith(TRUNCATED_MARKER):
        v = v[len(TRUNCATED_MARKER):].lstrip()
    if cut:
        return f"<story_state>\n{_TRUNCATED_NOTE}\n{v}\n</story_state>"
    return f"<story_state>\n{v}\n</story_state>"
