"""CP-3 · **the request path** — the turn where a plan is created or resumed.

Every V-LIVE round at CP-1, CP-2 and CP-3 returned `CANNOT DETERMINE` for the same mechanical
reason: *no request path reached the package*. `serve.py` gave the SURFACE a turn. This gives the
PLAN one, and it is the last piece before CP-3's own exit criterion is measurable at all.

WHAT THIS MODULE IS FOR, IN ONE SENTENCE
----------------------------------------
The conversation is a lossy carrier, and the runtime was relying on it to hold identifiers —
**61.8% of failures are on a declaration that already succeeded**. The plan is the carrier that does
not evict. This module is where a turn picks that carrier up.

🔴 **S3-M4: A SECOND MESSAGE DURING A LIVE PLAN ROUTES INTO IT.** It is not rejected and it does not
start a second plan. A hard reject is a ceiling — the user is mid-plan and says *"actually make it
chapter three"*, and refusing that is worse than having no plan at all. The database already makes
two live plans unrepresentable (a partial unique index); this module's job is to never *try*, so the
constraint stays a backstop rather than becoming the error path.

🔴 **A PLAN BLOCK THAT FAILS TO PARSE IS SURFACED, NEVER DROPPED.** The worst available outcome is a
model that believes it has a plan while the service has none: every later turn then binds against a
plan that does not exist, and the failure appears at a step nobody can trace back to the parse. C-12
gives the rejection a locus — line, field, what would have been accepted — and this module carries
it out rather than swallowing it into a log.

WHERE THE BOUNDARY IS
---------------------
`app.agentruntime` imports nothing but stdlib and itself, so it cannot reach a database; the
membrane gate enforces that. This module is on the OTHER side: it may hold both, and it is the only
place where a plan and a connection meet on the request path.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.agentruntime.plan import PlanError, Spec, State
from app.agentruntime.planparse import PlanParseError, parse
from app.agentruntime.planproject import project
from app.db import plans as plan_db

logger = logging.getLogger(__name__)

#: A fenced ```plan block. **A fence, not a heuristic.** The alternative considered and rejected was
#: scanning for `# goal:` anywhere in the reply — which is the backtick prose scraper CP-2.2 deleted,
#: in a new costume: a model quoting a plan back to the user would have silently authored one.
_PLAN_BLOCK = re.compile(r"```plan[ \t]*\r?\n(?P<body>.*?)```", re.DOTALL)

#: How the live plan reaches the model. A SYSTEM message, because the plan is state the runtime
#: knows and the model must not contradict — not a user instruction it may weigh against others.
PLAN_ROLE = "system"


@dataclass(frozen=True)
class PlanTurn:
    """The live plan as this turn sees it."""

    plan_id: str
    spec: Spec
    state: State
    projection: str

    @property
    def is_resume(self) -> bool:
        """True once anything has happened — the distinction S3-M4 turns on.

        A plan with no events yet is live but unstarted, and a message arriving then is still the
        *first* message of that plan. Calling it a resume would misreport the turn.
        """
        return bool(self.state.events)


@dataclass(frozen=True)
class PlanAdoption:
    """What a reply did to the session's plan. **Every field is required to be readable.**

    `rejected_with` is the reason this type exists rather than a bare `str | None`: an adoption that
    failed and an adoption that was never attempted are different facts, and collapsing them is the
    NULL-versus-`[]` confusion CP-2.7 item C already had to separate once.
    """

    attempted: bool
    plan_id: str | None
    version: int | None
    rejected_with: str | None

    @property
    def adopted(self) -> bool:
        return self.plan_id is not None


NOT_ATTEMPTED = PlanAdoption(attempted=False, plan_id=None, version=None, rejected_with=None)


async def live_plan_for_turn(pool, session_id) -> PlanTurn | None:
    """This session's live plan, projected for the prompt — or None.

    🔴 **TAKES A POOL AND ACQUIRES ONE CONNECTION**, because `load_live` issues two statements — the
    plan row, then its events — and on a pool those would run on two different connections with a
    window between them. A plan read against one snapshot and a history read against another is a
    replay of a state that never existed.

    **Returns None only when there is no plan.** A load failure raises, and deliberately: a plan row
    that cannot be rebuilt is a plan whose bindings nothing re-checked, and serving the turn as if
    the session were planless would hand the model a blank slate while the database says otherwise.
    That divergence is unrecoverable by the next turn, because the next turn would see the same row
    and make the same silent choice.
    """
    async with pool.acquire() as conn:
        loaded = await plan_db.load_live(conn, session_id)
    if loaded is None:
        return None
    plan_id, spec, state = loaded
    return PlanTurn(plan_id=plan_id, spec=spec, state=state,
                    projection=project(spec, state))


def plan_message(turn: PlanTurn) -> dict:
    """The system message that carries the plan into the model's context.

    The projection is used verbatim. `planproject` already declares whether it is abridged and
    guarantees that abridging never reaches an identifier — restating any of it here would create a
    second author for the same sentence, which is the drift `serve.statement_for` exists to prevent.
    """
    return {"role": PLAN_ROLE, "content": turn.projection}


def extract_plan_block(text: str) -> str | None:
    """The plan source in a reply, or None. **The FIRST block only.**

    Two blocks in one reply is not a plan, it is two plans and no statement of which is meant.
    Taking the first would pick by position; taking the last would pick by position differently.
    Neither is a decision the model made, so this refuses to make one for it — see
    `adopt_plan_from_reply`, which turns the ambiguity into a rejection with a reason.
    """
    found = _PLAN_BLOCK.findall(text or "")
    if len(found) != 1:
        return None
    return found[0]


async def adopt_plan_from_reply(pool, session_id, text: str) -> PlanAdoption:
    """Create or revise this session's plan from a fenced block in the reply.

    **Revision, not rejection.** A block arriving while a plan is live supersedes it as a new
    VERSION — `save_spec` does that atomically — so §0.8's approval invalidation stays inspectable
    after the fact instead of being reconstructed from memory. Refusing the revision would be the
    S3-M4 ceiling one level down: the model has replanned and the service would be holding the plan
    it replanned away from.

    🔴 **A POOL, AND THE PARSE HAPPENS BEFORE THE CONNECTION IS TAKEN.** Both matter. `save_spec`
    opens a transaction, and `asyncpg.Pool` has no `.transaction()` — passing a pool where a
    connection was meant raised `AttributeError` on the FIRST real turn that authored a plan, while
    every test stayed green because the fixture hands out a Connection. Fixture shape is not
    production shape. And holding a pooled connection across a parse would keep it for work that
    touches no database at all.
    """
    blocks = _PLAN_BLOCK.findall(text or "")
    if not blocks:
        return NOT_ATTEMPTED
    if len(blocks) > 1:
        return PlanAdoption(
            attempted=True, plan_id=None, version=None,
            rejected_with=(
                f"{len(blocks)} plan blocks in one reply, and nothing says which is meant. "
                f"Emit exactly one ```plan block, or none."
            ),
        )

    try:
        spec = parse(blocks[0])
    except PlanParseError as exc:
        # C-12 — the locus travels. `str(exc)` already carries line, reason and what would have
        # been accepted; re-wording it here would lose the line number, which is the only part a
        # model can act on.
        return PlanAdoption(attempted=True, plan_id=None, version=None, rejected_with=str(exc))
    except PlanError as exc:
        # §6.2's construction-time binding check, reached through the parser. A step that binds to
        # something no earlier step emits CANNOT be constructed — so this arrives as a refusal to
        # build the object, not as a plan that fails later at the step that needed the value.
        return PlanAdoption(attempted=True, plan_id=None, version=None, rejected_with=str(exc))

    async with pool.acquire() as conn:
        live = await plan_db.load_live(conn, session_id)
        version = (live[1].version + 1) if live else 1
        if version != 1:
            spec = Spec(
                goal=spec.goal, steps=spec.steps, done_when=spec.done_when,
                template_id=spec.template_id, template_version=spec.template_version,
                replan_budget=spec.replan_budget, version=version,
            )
        plan_id = await plan_db.save_spec(conn, session_id, spec)
    logger.info(
        "plan %s for session %s: v%d, %d step(s), %d gated",
        "revised" if version > 1 else "created", session_id, version,
        len(spec.steps), sum(1 for s in spec.steps if s.gated),
    )
    return PlanAdoption(attempted=True, plan_id=plan_id, version=version, rejected_with=None)
