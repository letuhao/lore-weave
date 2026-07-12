"""Track C Phase 2 — the RAIL DRIVER: server-side progress + book-state grounding.

The problem this exists to solve, stated exactly:

    Post-WS-3 the pinned rail works. Discovery is dead (0 `find_tools` calls), the user's
    assent lands on the rail, the step tools are advertised, the errors are honest. And the
    flagship STILL does not ship — measured across four identical S06 runs:
    kinds 5/12/0/5 · **cast 0/0/0/0** · plan 0/1/0/0.

    Nothing DRIVES the rail. The model is handed a 12-step recipe and asked to hold it
    across a 17-turn conversation while also doing the emotional work of a co-writing
    scene — and it drops it. Each user turn gets answered on its own terms. The old rail
    header literally said *"look back at what you have already called, and continue from
    the first step still outstanding"*: it asked the model to REMEMBER, and remembering is
    the thing it is worst at.

So stop asking. Compute where the user actually is, on the server, every turn, and TELL the
model its next single action. Two independent sources, neither of which is the model's memory:

1. **The artifact** (`book_state`) — "the world has 12 categories; 0 cast members are saved."
   Read from the SSOT. This is the STRONGER signal, and it is the one that catches the
   failure mode that has cost this project the most: a tool that was *called* and quietly
   did nothing. A step whose tool ran but whose artifact never landed is NOT done, and the
   book is the only thing that knows that.

2. **The call log** (`chat_messages.tool_calls`) — "you already called `glossary_adopt_standards`
   successfully." Used for steps whose effect is not an artifact (a read, a confirm), where
   there is nothing in the book to point at.

A step is DONE if its `done_when` predicate holds against the book, else if its tool
succeeded in this session, else it is NOT DONE. The first not-done step is the next action.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── the `done_when` grammar (C3 contract extension) ──────────────────────────
#
# CLOSED SET, deliberately tiny, and parsed — never `eval`'d. A workflow step may declare
# `"done_when": "cast > 0"`, meaning "this step's effect is visible in the book as at least
# one cast member". Anything outside this grammar is REJECTED and logged, never silently
# treated as satisfied: a mis-typed predicate that quietly reads as "done" would march the
# agent straight past the step it most needed to take.
BOOK_STATE_KEYS = (
    "categories",    # glossary book_kinds        — the world's categories
    "cast",          # glossary_entities          — characters/places/things saved
    "connections",   # knowledge_projects stats   — the KG projection
    "plan",          # composition plan_run/spec  — the arc plan
    "chapters",      # book chapters              — chapters that exist
    "prose",         # book chapters with text    — chapters actually written
)

_PREDICATE_RE = re.compile(r"^\s*(\w+)\s*(>=|>)\s*(\d+)\s*$")


@dataclass
class BookState:
    """Counts read from the SSOT. ``None`` means UNKNOWN (the probe for that source failed
    or was not run) — which is emphatically NOT the same as 0 ("confirmed empty").

    Conflating the two is how a grounding block starts lying: an unreachable glossary
    would otherwise read as "you have no categories", and the agent would helpfully rebuild
    a world the user already has."""

    categories: int | None = None
    cast: int | None = None
    connections: int | None = None
    plan: int | None = None
    chapters: int | None = None
    prose: int | None = None
    # Which sources failed this turn (for logging + so the renderer can stay quiet about them)
    failed_sources: list[str] = field(default_factory=list)

    def get(self, key: str) -> int | None:
        return getattr(self, key, None) if key in BOOK_STATE_KEYS else None

    @property
    def any_known(self) -> bool:
        return any(self.get(k) is not None for k in BOOK_STATE_KEYS)


def parse_done_when(expr: str) -> tuple[str, str, int] | None:
    """Parse a `done_when` predicate into ``(key, op, threshold)``.

    Returns None for anything unparseable or referencing an unknown key — and LOGS it. A
    silently-ignored predicate is a step that can never be marked done (or worse, one the
    caller decides to treat as done); either way the author must hear about it."""
    if not isinstance(expr, str) or not expr.strip():
        return None
    m = _PREDICATE_RE.match(expr)
    if not m:
        logger.warning(
            "workflow step has an unparseable done_when %r — expected '<key> > <n>' "
            "with key in %s; the step will fall back to the call log",
            expr, list(BOOK_STATE_KEYS),
        )
        return None
    key, op, num = m.group(1), m.group(2), int(m.group(3))
    if key not in BOOK_STATE_KEYS:
        logger.warning(
            "workflow step's done_when references unknown book-state key %r "
            "(known: %s) — falling back to the call log",
            key, list(BOOK_STATE_KEYS),
        )
        return None
    return key, op, num


def _predicate_holds(state: BookState, key: str, op: str, num: int) -> bool | None:
    """True/False, or None when the book-state value is UNKNOWN."""
    val = state.get(key)
    if val is None:
        return None
    return val > num if op == ">" else val >= num


@dataclass
class StepProgress:
    index: int              # 1-based position in the rail
    step_id: str
    tool: str
    done: bool
    reason: str             # why we believe that — shown to nobody, logged for us


@dataclass
class RailProgress:
    slug: str
    steps: list[StepProgress]
    next_index: int | None          # 1-based; None ⇒ every step is done
    state: BookState

    @property
    def next_step(self) -> StepProgress | None:
        if self.next_index is None:
            return None
        return self.steps[self.next_index - 1]

    @property
    def all_done(self) -> bool:
        return self.next_index is None


def compute_rail_progress(
    slug: str,
    steps: list[dict],
    state: BookState,
    succeeded_tools: set[str],
) -> RailProgress:
    """Where is the user, really?

    ``steps`` are the rail steps (each may carry ``done_when``). ``succeeded_tools`` are the
    tools that have already run SUCCESSFULLY in this session (from the persisted tool-call
    history — the server's own record, not the model's recollection).

    The artifact wins over the call log, and that ordering is the point: a step whose tool
    was called but whose artifact never landed is NOT done. That is precisely the flagship's
    signature failure — `glossary_propose_entities` returning "success" while 0 entities
    were created — and grounding on the book is what refuses to be fooled by it.
    """
    # ── pass 1: the ARTIFACT verdict, per step ───────────────────────────────
    # Hard in BOTH directions where the book can answer: present ⇒ done, absent ⇒ NOT done
    # (even if the tool "succeeded"). Only an UNKNOWN book-state falls through.
    artifact: dict[int, bool] = {}
    for i, st in enumerate(steps, 1):
        parsed = parse_done_when(st.get("done_when", ""))
        if parsed is None:
            continue
        holds = _predicate_holds(state, *parsed)
        if holds is not None:
            artifact[i] = holds

    # The furthest point the pipeline has CONTIGUOUSLY reached from the start. A rail is a
    # pipeline, so an unbroken run of present artifacts is proof the plumbing up to that point
    # ran — you cannot be holding 3187 cast members without the categories they are filed
    # under. This is what lets a NEW session on an EXISTING book resume mid-rail instead of
    # being told to start from step 1 on a book that already has 31 categories.
    #
    # CONTIGUOUS is load-bearing, and the review caught why. The first cut used
    # max(any TRUE artifact), which jumped OVER a proven-ABSENT one: a book with chapters but
    # 0 categories marked `adopt-categories` (the confirm_token producer) "done — do not
    # repeat", then named its confirm as the next action — a deadlock, because the token it
    # needs comes from the step now forbidden. Stopping at the first proven-absent artifact
    # means a gap in the pipeline resets the resume point to before the gap, where it belongs.
    last_artifact_done = 0
    for i in sorted(artifact):
        if not artifact[i]:
            break
        last_artifact_done = i

    # A `confirm` gate exists only to apply the step before it, and it names that step in
    # its inputs_map (e.g. apply-cast ← save-cast.confirm_token). It is therefore done
    # exactly when the step it confirms is done — a confirm has no artifact of its own, and
    # it is not independently actionable (it needs a token from a call that already happened).
    confirms: dict[int, int] = {}
    by_id = {str(st.get("id") or ""): i for i, st in enumerate(steps, 1)}
    for i, st in enumerate(steps, 1):
        if st.get("gate") != "confirm":
            continue
        imap = st.get("inputs_map")
        if not isinstance(imap, dict):
            continue
        for ref in imap.values():
            src = str(ref).split(".", 1)[0]
            if src in by_id and by_id[src] != i:
                confirms[i] = by_id[src]
                break

    # Call-log doneness CONSUMES occurrences in step order, so a rail that uses the same tool
    # in two steps needs TWO successes to mark both done — not one, which a bare
    # `tool in succeeded_tools` would (a review finding). `succeeded_tools` may be a set (each
    # tool counts once) or a Counter (true per-tool counts); Counter() accepts both.
    from collections import Counter

    remaining: Counter = Counter(succeeded_tools)

    def _consume(tool: str) -> bool:
        if remaining[tool] > 0:
            remaining[tool] -= 1
            return True
        return False

    out: list[StepProgress] = []
    for i, st in enumerate(steps, 1):
        tool = str(st.get("tool") or "")
        step_id = str(st.get("id") or f"step-{i}")

        if i in artifact:
            if artifact[i]:
                key = parse_done_when(st.get("done_when", ""))[0]
                done, reason = True, f"the book shows {key}={state.get(key)}"
            else:
                # The artifact is ABSENT. Overrides a successful-looking call and overrides
                # the pipeline backfill: the tool may have run and written nothing, which is
                # exactly the bug this whole mechanism refuses to be fooled by.
                key = parse_done_when(st.get("done_when", ""))[0]
                done, reason = False, f"the book shows {key}={state.get(key)} — the effect never landed"
        elif st.get("done_when"):
            # It declared an artifact but the book could not be reached this turn. Fall back
            # to the call log rather than guess: guessing "done" skips a step, guessing "not
            # done" redoes one.
            done = _consume(tool)
            reason = f"book-state unknown (probe failed); {'the tool ran' if done else 'the tool has not run'}"
        elif i in confirms:
            src = confirms[i]
            done = out[src - 1].done if src <= len(out) else _consume(tool)
            reason = f"confirms {steps[src - 1].get('id')}, which is {'done' if done else 'not done'}"
        elif _consume(tool):
            done, reason = True, "the tool ran successfully"
        elif i < last_artifact_done:
            done = True
            reason = "a later step's artifact exists — the pipeline already ran past this"
        else:
            done, reason = False, "the tool has not run"

        out.append(StepProgress(index=i, step_id=step_id, tool=tool, done=done, reason=reason))

    next_index = next((s.index for s in out if not s.done), None)
    return RailProgress(slug=slug, steps=out, next_index=next_index, state=state)


# ── rendering ────────────────────────────────────────────────────────────────

# The labels must say what the NUMBER actually is, not what the step is about. "connections"
# is the KG node count (how many cast members are in the connection map), and "plan" is a
# plan-existence flag, not a count of plans — a review caught both misreporting their unit.
_STATE_LABELS = {
    "categories": "world categories",
    "cast": "characters/places saved",
    "connections": "cast members placed in the connection map",
    "plan": "arc plan started (1 = yes)",
    "chapters": "chapters",
    "prose": "chapters with writing in them",
}


def render_book_state(state: BookState) -> str | None:
    """The one-line factual snapshot. Only KNOWN values appear — an unknown source is simply
    not mentioned, because inventing "0" for an unreachable service would tell the agent the
    user's world is empty when it may be full."""
    bits = [
        f"{_STATE_LABELS[k]}: {state.get(k)}"
        for k in BOOK_STATE_KEYS
        if state.get(k) is not None
    ]
    return " · ".join(bits) if bits else None


def render_progress_block(progress: RailProgress) -> str:
    """What the model reads instead of trying to remember.

    THE DIVISION OF LABOUR — and it took two live failures to get it right.

    This block answers exactly one question: **WHERE** in the recipe this book stands. It says
    nothing whatever about **WHEN** to act. That stays with the model, because only the model
    can hear the user assent, and the pinned rail's own header already tells it how ("run this
    when they ask — or when they simply agree to your offer").

    Cut 1 gave the model an unconditional imperative: *"call `glossary_list_system_standards`
    NOW — the user already said yes."* On turn 1 of S06 the user has said no such thing; they
    are three sentences into describing a story they have carried for years. The agent fired
    the opening step **while they were still talking**, twice, and by the time the real assent
    arrived at turn 7 it had burned the opening of the rail. Cast: 0.

    Cut 2 over-corrected: hold the imperative until the rail is "in flight", defined as *an
    artifact exists*. But the rail's first three steps create no artifact — they read the
    standards, adopt them, and confirm. So "in flight" could never become true, the block said
    *"don't start building on your own"* forever, and the agent re-ran step 1 on every turn it
    tried. A deadlock, and a worse one: it now actively told the model NOT to do the thing.
    Cast: 0 again.

    The lesson both times: **a driver that tries to own WHEN will either interrupt the user or
    stall the rail.** Own WHERE — which the model genuinely cannot know and constantly gets
    wrong — and leave WHEN alone.
    """
    lines: list[str] = []

    snapshot = render_book_state(progress.state)
    if snapshot:
        lines.append(
            "WHERE THE BOOK ACTUALLY IS (read from the book itself just now — "
            "trust this over your own memory of the conversation):"
        )
        lines.append(f"  {snapshot}")
        lines.append("")

    nxt = progress.next_step
    if nxt is None:
        lines.append(
            "EVERY step of this recipe is already done for this book. Do NOT run it again. "
            "Talk to the user about what you built, and ask what they want next."
        )
        return "\n".join(lines)

    done = [s for s in progress.steps if s.done]
    if done:
        lines.append(
            "ALREADY DONE for this book — do NOT repeat these: "
            + ", ".join(s.step_id for s in done)
        )
    lines.append(
        f'YOUR PLACE IN THE RECIPE: step {nxt.index} of {len(progress.steps)}, '
        f'"{nxt.step_id}" → `{nxt.tool}`.'
    )
    if done:
        # Only meaningful when work IS already behind us. Saying "NOT step 1" while step 1
        # is literally the named next step is a contradiction, and a contradiction in a
        # system prompt is worse than silence — the model has to resolve it, and it resolves
        # it by doing nothing.
        lines.append(
            "  When you run the recipe, resume HERE — not at step 1, and not at any step "
            "listed above as already done. Repeating a finished step wastes the user's turn "
            "and builds nothing."
        )
    remaining = [s for s in progress.steps if not s.done and s.index != nxt.index]
    if remaining:
        lines.append("  After that, in order: " + ", ".join(s.step_id for s in remaining))
    return "\n".join(lines)
