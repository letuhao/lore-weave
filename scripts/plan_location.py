"""plan_location — where the knowledge-architecture plan lives, live or archived.

WHY THIS EXISTS
───────────────
Ten scripts hardcoded `docs/plans/2026-08-09-knowledge-architecture-refactor.md`. T49's last
clause is `/aif-archive`, which MOVES that file to `.ai-factory/archive/plans/`. Measured
before doing it, the move would have:

  * hard-FAILED `plan-final-verification` (loud, correct),
  * crashed the three gates with no guard at all (loud, acceptable),
  * and turned `plan-row-honesty-gate` SILENTLY GREEN — its missing-file branch printed
    `SKIP` and returned 0.

That last one is the shape this repo keeps paying for: archiving a document would have
disarmed the guard that checks the document, and the suite would have stayed green while it
happened. A gate whose subject has vanished has not passed; it has stopped looking.

So the plan is resolved through ONE function that knows both locations. Archiving then
changes where the file is and nothing else, and a plan that is in NEITHER place is an error
every caller can see rather than a quiet zero.
"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN_NAME = "2026-08-09-knowledge-architecture-refactor.md"

#: Live first, then the archive. Order matters only while both exist (during the archiving
#: commit itself); after it, exactly one does.
PLAN_SEARCH = (
    os.path.join(ROOT, "docs", "plans", PLAN_NAME),
    os.path.join(ROOT, ".ai-factory", "archive", "plans", PLAN_NAME),
)


def plan_path() -> str:
    """The plan's current location. Returns the LIVE path when it is nowhere.

    Returning a path rather than raising keeps every caller's own missing-file message —
    each says something different and more useful than a shared exception would.
    """
    for p in PLAN_SEARCH:
        if os.path.exists(p):
            return p
    return PLAN_SEARCH[0]


def plan_found() -> bool:
    """True when the plan exists in either location.

    Callers that treated "missing" as a pass must use this and FAIL instead: the archived
    plan is still the subject, and a gate that cannot find its subject has not verified it.
    """
    return any(os.path.exists(p) for p in PLAN_SEARCH)
