"""T37 LIVE SMOKE — a plan revision closes its own stale role, and NOTHING else.

Runs INSIDE lw-iso-composition-service against the live glossary over real HTTP, through the
production `KalClient` and the production `publish_planned_roles` / `close_stale_planned_roles`.
No fakes: the fake-KAL unit tests already pass, and what they cannot prove is that the REAL
read carries `origin` at all - which is precisely the bug T37d found and fixed.

The safety property, live:
  1. plan appends two roles          -> origin='plan', both open
  2. the author declares one         -> origin='author', open
  3. a REVISION drops plan role #2   -> #2 closes, #1 stays open, the AUTHOR's stays open,
                                        and the unmarked legacy facts are untouched

WHAT IT FOUND ON ITS FIRST RUN, which is why it is committed rather than thrown away:
`close_stale_planned_roles` closed at `introduce_at * STRIDE` — the SAME ordinal
`publish_planned_roles` opens the role at. The story interval is half-open, so glossary
answered `422 GLOSS_INVALID "valid_to_ordinal must be greater than the fact's
valid_from_ordinal"` and the pipeline swallowed it by design. **Every close failed live while
six unit tests were green**, because a fake KAL has no interval to violate.

RUN IT (needs the lw-iso stack up and the images REBUILT from the current tree):

    docker cp services/composition-service/scripts/live_smoke_t37_revision.py \\
        lw-iso-composition-service-1:/tmp/s.py
    docker exec -e SMOKE_BOOK=<book uuid> -e SMOKE_ENTITY=<entity uuid> \\
                -e SMOKE_USER=<user uuid> -e SMOKE_TAG=t37smoke$(date +%s) \\
        lw-iso-composition-service-1 python /tmp/s.py

SMOKE_TAG must be unique per run: it prefixes every predicate so the run owns its rows and
can assert on them without tripping over roles a previous run left behind. Exit 0 = all live
checks passed.
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, "/app")

from app.clients.kal_client import get_kal_client
from app.engine.planning_pipeline import (
    KG_EVENT_ORDER_CHAPTER_STRIDE, close_stale_planned_roles, publish_planned_roles,
)


class Char:
    def __init__(self, name, roles):
        self.name, self.roles = name, roles


BOOK = uuid.UUID(os.environ["SMOKE_BOOK"])
ENT = os.environ["SMOKE_ENTITY"]
USER = uuid.UUID(os.environ["SMOKE_USER"])
TAG = os.environ["SMOKE_TAG"]          # unique predicate prefix so the smoke owns its rows

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not cond:
        fails.append(name)


async def main():
    # The PRODUCTION factory, not a hand-built client: the base URL, the token and the
    # timeout are then exactly what a real planning run uses. Building one by hand is how the
    # first attempt at this smoke pointed at glossary-service and got a 404 - the KAL is a
    # knowledge-gateway surface, and a smoke that configures itself can be wrong in a way the
    # thing it is testing is not.
    kal = get_kal_client()
    print(f"  KAL base = {kal._base_url}")

    id_by_name = {"Kai": ENT}
    introduce_at = {"Kai": 3}
    p1, p2 = f"{TAG}_betrayed", f"{TAG}_guards"

    # ---- 1. the PLAN writes two roles -------------------------------------------------
    n = await publish_planned_roles(
        kal, BOOK,
        cast_objs=[Char("Kai", [{"predicate": p1, "object": "Mira"},
                                {"predicate": p2, "object": "the Gate"}])],
        id_by_name=id_by_name, introduce_at=introduce_at, user_id=USER)
    check("plan appended 2 roles over real HTTP", n == 2, f"written={n}")

    # ---- 2. the AUTHOR declares one on the SAME entity ---------------------------------
    await kal.append_role_fact(
        BOOK, subject_entity_id=ENT, predicate=f"{TAG}_sworn_to", object_value="Ada",
        valid_from_ordinal=1 * KG_EVENT_ORDER_CHAPTER_STRIDE, user_id=USER, origin="author")

    # ---- 3. read back through the REAL client — this is the T37d fix under test --------
    facts = await kal.open_facts_for(BOOK, ENT, user_id=USER)
    mine = [f for f in facts if str(f.get("attr_or_predicate", "")).startswith(TAG)]
    check("the real read returns 3 open facts", len(mine) == 3, f"got={len(mine)}")
    origins = sorted(str(f.get("origin")) for f in mine)
    check("the real read CARRIES origin (T37d: the read was blind)",
          origins == ["author", "plan", "plan"], f"origins={origins}")

    # ---- 4. the REVISION keeps role #1 and drops role #2 -------------------------------
    closed = await close_stale_planned_roles(
        kal, BOOK,
        cast_objs=[Char("Kai", [{"predicate": p1, "object": "Mira"}])],   # p2 dropped
        id_by_name=id_by_name, introduce_at=introduce_at, user_id=USER)
    # NOT `closed == 1`. The entity carries plan-origin roles from EARLIER runs of this smoke,
    # and closing those is correct — a role a previous plan wrote and this one does not imply
    # is the definition of stale. Asserting a global count would have made right behaviour
    # look like a bug. Scope the claim to the facts this run owns instead.
    check("the revision closed at least this run's stale role", closed >= 1, f"closed={closed}")

    # ---- 5. what survived --------------------------------------------------------------
    after = await kal.open_facts_for(BOOK, ENT, user_id=USER)
    still = {str(f.get("attr_or_predicate")) for f in after
             if str(f.get("attr_or_predicate", "")).startswith(TAG)}
    check("exactly ONE of THIS run's roles closed", {p1, f"{TAG}_sworn_to"} == still,
          f"open={sorted(still)}")
    check("the role the revision STILL implies is open", p1 in still)
    check("the role the revision DROPPED is closed", p2 not in still)
    check("the AUTHOR's role SURVIVED a plan revision", f"{TAG}_sworn_to" in still,
          f"open={sorted(still)}")

    print("\n  " + (f"{len(fails)} failure(s)" if fails else "all live checks passed"))
    return 1 if fails else 0


sys.exit(asyncio.run(main()))
