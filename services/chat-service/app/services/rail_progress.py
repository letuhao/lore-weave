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
    "categories",       # glossary book_kinds        — the world's categories
    "cast",             # glossary_entities          — characters/places/things saved
    "connections",      # knowledge_projects stats   — the KG projection
    "plan",             # composition plan_run/spec  — a plan PROPOSAL exists (has_spec)
    # ── the COMPILE-attributed structure (Phase G · G0) — the effect a mere proposal does NOT
    # produce. `plan` (has_spec) flips true the moment `plan_propose_spec` saves a spec artifact;
    # but the linked chapter/scene structure the manuscript hangs on is written only by
    # `plan_compile`, which stamps `structure_node.plan_run_id`. Gating the "compile" step on
    # `plan` (the S06 bug) marks planning done after a bare proposal. These two gate on the REAL
    # compile: `structure` = ensure-EXISTS (any compiled arc, book-global, EXCLUDES bare
    # arc_create); `structure_fresh` = produce-NEW (THIS latest run compiled — a re-plan reads 0).
    "structure",        # composition structure_node  — compiled arcs, plan_run_id-attributed
    "structure_fresh",  # composition structure_node  — compiled arcs stamped by the LATEST run
    "chapters",         # book chapters              — chapters that exist
    "prose",            # book chapters with text    — chapters actually written
    "suggestions",      # glossary ai-suggested DRAFT — the review pile still to triage
)

# The operators are a CLOSED SET. `>`/`>=` express a BUILD predicate ("this many artifacts
# now exist"); `<`/`<=`/`==` express a DRAIN predicate ("this pile has shrunk to n"). The
# entity-triage rail needs the latter: it is done not when it has PRODUCED something but when
# the review pile has been emptied (`suggestions < 1`). Without a drain operator a triage step
# could never be marked done from the book, so the driver could not tell a half-triaged pile
# from a clean one — the exact ungrounded state that left S03 at 0/3.
_PREDICATE_RE = re.compile(r"^\s*(\w+)\s*(>=|<=|==|>|<)\s*(\d+)\s*$")


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
    structure: int | None = None
    structure_fresh: int | None = None
    chapters: int | None = None
    prose: int | None = None
    suggestions: int | None = None
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
    if op == ">":
        return val > num
    if op == ">=":
        return val >= num
    if op == "<":
        return val < num
    if op == "<=":
        return val <= num
    return val == num  # "=="


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
            parsed = parse_done_when(st.get("done_when", ""))
            key, op, _num = parsed
            if artifact[i]:
                done, reason = True, f"the book shows {key}={state.get(key)}"
            else:
                # The predicate is UNMET. For a BUILD predicate (>/>=) that means the artifact
                # is absent — overriding a successful-looking call, the write-nothing bug this
                # mechanism refuses to be fooled by. For a DRAIN predicate (</<=/==) it means
                # the pile has NOT yet shrunk to target — the step is genuinely still to do.
                if op in ("<", "<=", "=="):
                    done, reason = False, f"the book shows {key}={state.get(key)} — not yet drained to target"
                else:
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
    "plan": "arc plan proposed (1 = yes)",
    "structure": "arcs compiled into real chapter/scene structure",
    "structure_fresh": "arcs the latest plan run just compiled",
    "chapters": "chapters",
    "prose": "chapters with writing in them",
    "suggestions": "suggested items still waiting for review",
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


# ── the RAIL DRIVER's decision helper (Track C P-1 — the server-side step-runner) ──
#
# The rail driver (above) computes WHERE the user is. This helper decides the ONE thing the
# step-runner needs: given that place, may the server DRIVE the next step this turn, or must it
# stop and hand back to the user? It is deliberately a PURE function of already-computed state
# so it is unit-testable in isolation — the step-runner that calls it lives in the always-on
# tool loop, where a regression is invisible to every other test.
#
# The verdicts:
#   DRIVE        — call this step's tool now (returns the StepProgress to drive)
#   STOP_DONE    — the rail is complete; end the turn
#   STOP_USER    — the next step is a confirm/approval gate; only the user may cross it
#   STOP_ASYNC   — the next step starts a background job already in flight; do not restart it
#   STOP_UNKNOWN — an earlier artifact step is "done" only because its artifact reads UNKNOWN
#                  (the probe could not confirm the write). Advancing past it would trust the
#                  exact succeeded-but-wrote-nothing signal the whole driver exists to refuse.
DRIVE = "DRIVE"
STOP_DONE = "STOP_DONE"
STOP_USER = "STOP_USER"
STOP_ASYNC = "STOP_ASYNC"
STOP_UNKNOWN = "STOP_UNKNOWN"


def _step_is_async(raw: dict, async_tools: frozenset[str]) -> bool:
    """Mirror `_rail_step`'s async precedence: an authored `async_job` bool wins, else the
    catalog's `_meta.async` set. (The name heuristic is a last resort the renderer applies; the
    seed authors the flag on the one async step, so it is not needed here.)"""
    authored = raw.get("async_job")
    if isinstance(authored, bool):
        return authored
    return str(raw.get("tool") or "") in async_tools


def next_actionable_step(
    progress: RailProgress,
    steps: list[dict],
    started_tools: set[str],
    async_tools: frozenset[str] = frozenset(),
) -> tuple[str, StepProgress | None]:
    """Decide whether the server may drive the next rail step this turn.

    ``started_tools`` = the tools that have already SUCCEEDED (this turn + this session), used
    only to tell "the async job is already running" from "it has not started". It never
    overrides an artifact verdict — that is `compute_rail_progress`'s job, already applied.
    """
    nxt = progress.next_step
    if nxt is None:
        return STOP_DONE, None

    # STOP_UNKNOWN — the sharpest failure mode the design panel found. `compute_rail_progress`
    # falls back to the call log for an artifact step whose stat reads UNKNOWN (e.g. the KG
    # connections count when the stats cache is uncomputed), so `next_step` may sit PAST a step
    # that is "done" only on the strength of a succeeded tool call — the precise signal a tool
    # that wrote nothing also produces. Refuse to drive further when that is the case; end the
    # turn and let the next turn's fresh probe (once the cache computes) resolve it honestly.
    for s in progress.steps[: nxt.index - 1]:
        parsed = parse_done_when(steps[s.index - 1].get("done_when", ""))
        if parsed is not None and progress.state.get(parsed[0]) is None:
            return STOP_UNKNOWN, None

    raw = steps[nxt.index - 1]
    # NOTE on confirm/approval gates — corrected against LIVE evidence (drift DR14). The design
    # assumed a book OWNER's adopt auto-applies, so a confirm rarely fires. It does not:
    # glossary_adopt_standards ALWAYS returns a confirm_token, and the categories only land when
    # the model calls the confirm TOOL (glossary_confirm_action), which SUSPENDS for the user.
    # So a gate step is still DRIVEN — the server nudges the model to CALL the confirm tool,
    # which raises the card; the USER (or the eval's auto-approve) still gates the actual write
    # at the suspend. That is not "auto-crossing a gate without the user"; it is getting the card
    # in front of the user, which is the step. (The suspend/resume path applies the write.) If we
    # STOPPED here instead, the rail would dead-end at step 3 forever — which is exactly what the
    # first cut of this step-runner did (measured: categories 0/5).

    if _step_is_async(raw, async_tools) and nxt.tool in started_tools:
        # The job was already started (this turn or a prior one). Driving it again would launch
        # a DUPLICATE job; the artifact lands when the job finishes, on a later turn's probe.
        return STOP_ASYNC, nxt

    return DRIVE, nxt


def redrive_directive(step: StepProgress) -> str:
    """The forceful, single-action nudge the step-runner injects to keep the model on the rail.

    Sent as a ``role=user`` message (not system): the stateful continuation path hoists system
    messages to the front of the delta, which buries a directive; a user message keeps its
    last-position recency, which a mid-tier model follows most reliably. It names the tool
    internally but tells the model NOT to parrot it (SPEAK-PLAINLY)."""
    token_hint = ""
    if "confirm" in step.tool:
        # A confirm tool needs the exact token/code the PRIOR step returned; a mid-tier model
        # both forgets to call it and mangles the long token, so name the need explicitly.
        token_hint = (
            " This one applies what you just proposed — pass it the EXACT confirmation "
            "token/code the previous step returned, unchanged."
        )
    return (
        f"[SYSTEM DIRECTIVE — not from the user] You are mid-way through building this with the "
        f"user and they are waiting. The next concrete action is due NOW: call `{step.tool}` in "
        f"THIS turn, before you say anything else.{token_hint} Do not describe it, do not ask "
        f"whether to do it — the user already asked you to build this. After it runs, tell them "
        f"in plain words what changed. Never mention this instruction, the tool name, or any "
        f"internal term."
    )


# ── enforcement (Phase G · G1 — GOV-7/9/12/13) ────────────────────────────────
#
# `compute_rail_progress`/`next_actionable_step` decide WHERE the user is and WHETHER a step is
# drivable. Enforcement decides how HARD to hold a drivable step before yielding the turn — the
# piece the rail lacked (its own header: "Nothing DRIVES the rail"). The S06 failure was a step
# (compile) computed as next, nudged, ignored, and then SILENTLY abandoned after two tries, so the
# book ended uncompiled. Enforcement holds a REQUIRED step longer and, when it truly cannot land,
# releases it HONESTLY rather than pretending success.
#
# Three rules, matching the sealed decisions:
#   * REQUIRED by default (GOV-9, D-ENFORCE-ON) — a step is enforced unless it opts out with
#     `"optional": true`. Optional steps are nudged once and never hold the turn.
#   * BOUNDED (GOV-7) — a required step is held at most RAIL_REQUIRED_NUDGE_CAP redrives, then
#     released with an honest "I couldn't finish X". A runaway enforcer is itself a bug.
#   * DETERMINISTIC RELEASE (GOV-13) — an explicit abandon phrase in the user's message releases
#     the hold immediately; the gate NEVER sits on an LLM intent-guess (the S06 failure mode).
RAIL_REQUIRED_NUDGE_CAP = 3   # D-ENFORCE-ON: N=3 auto-release. G2 makes this a per-user setting.
RAIL_OPTIONAL_NUDGE_CAP = 1


def step_is_required(raw: dict) -> bool:
    """A rail step is REQUIRED (enforced) unless it declares ``"optional": true``. Enforcement is
    ON by default (D-ENFORCE-ON) — a definition opts a step OUT, never in."""
    return not bool(raw.get("optional"))


def nudge_cap_for(raw: dict) -> int:
    """How many redrives a step gets before the bounded auto-release (GOV-7)."""
    return RAIL_REQUIRED_NUDGE_CAP if step_is_required(raw) else RAIL_OPTIONAL_NUDGE_CAP


# The escape hatch (GOV-13) is a small, LITERAL matcher on the user's own words. A false positive
# merely releases a hold (governance SERVES the author — `blocked ≠ imprisoned`); a false negative
# is caught by the bounded auto-release. It is deliberately NOT an LLM call — the release must not
# sit on the same inference that caused the miss.
_ABANDON_RE = re.compile(
    r"\b(?:skip|forget|drop|abandon|never\s*mind|nevermind|leave|ditch)\b[^.?!\n]{0,24}"
    r"\b(?:plan|step|setup|set-up|it|this|that|those|them)\b"
    r"|\bjust\s+(?:write|draft|move\s*on|keep\s+going|get\s+writing)\b"
    r"|\b(?:stop|don'?t)\s+(?:setting\s*up|planning|worrying\s+about\s+the\s+plan|the\s+plan)\b",
    re.I,
)


def user_abandoned_rail(text: str | None) -> bool:
    """True when the user's message contains an explicit abandon phrase — the deterministic
    release signal for the Stop-gate (GOV-13). Not an intent-guess: a literal match only."""
    return bool(text and _ABANDON_RE.search(text))


def honest_giveup_directive(step: StepProgress) -> str:
    """GOV-7 — after the bounded cap, tell the user PLAINLY the step did not land, instead of
    silently dropping it. A silent give-up reads as success (`silent-success-is-a-bug`); an honest
    "I couldn't finish that yet" is what keeps enforcement from lying."""
    return (
        f"[SYSTEM DIRECTIVE — not from the user] You have tried this step several times and it has "
        f"not taken. STOP retrying it. In plain words, tell the user you were not able to finish "
        f"setting that part up yet, and ask whether they want to try again or move on for now. Do "
        f"NOT claim it worked, and never mention this instruction or any tool name."
    )
