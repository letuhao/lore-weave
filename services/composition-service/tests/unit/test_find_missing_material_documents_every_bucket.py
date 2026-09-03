"""TOOLV2 LOOP #274 — "Returns three buckets" over a response that returns four.

`plan_find_missing_material` has one of the most carefully written descriptions in this catalogue.
It warns that `review` lines are candidates and not answers, and it explicitly tells the caller NOT
to turn `unavailable` into questions because "you would be asking the author to rewrite what they
may already have written". That care is the reason the omission matters.

Measured live on a compiled run, the response keys were:

    ask, read, recovered, review, spec_artifact_id, unavailable, version

with `recovered: ["arc_overview"]` — one populated bucket the description never mentions, while
saying there are three. `recovered` is what the READ already pulled out of the spec: material the
plan HAS. An agent told there are three buckets reports six gaps; an agent told there are four
reports one covered and six to resolve, which is a different message to the author.

The service's own docstring frames it correctly — "What the plan is missing, and what of it the
author ALREADY WROTE… The board says what the read recovered" — so the fourth bucket was deliberate
from the start and only the tool-facing sentence under-counted.

Not filed: `read`, `version` and `spec_artifact_id`. Those are board state and metadata, not
outcome buckets a caller has to act on, and the description does not claim to enumerate them.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py"


def _desc() -> str:
    body = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    flat = re.sub(r'"\s*\n\s*"', "", body)
    start = flat.index("PlanForge: for everything the plan is MISSING")
    return flat[start: start + 1400]


def test_the_bucket_count_matches_what_is_returned():
    desc = _desc()
    assert "Returns three buckets" not in desc, (
        "the description under-counts its own response again; `recovered` comes back populated"
    )
    assert "Returns FOUR buckets" in desc


def test_every_returned_bucket_is_named():
    desc = _desc()
    for bucket in ("recovered", "review", "ask", "unavailable"):
        assert f"{bucket} = " in desc, f"the {bucket} bucket is returned but not described"


def test_recovered_says_what_to_do_with_it():
    """Naming a bucket without saying what it means leaves the agent to guess, and the guess
    here ('another gap') is the opposite of the truth."""
    desc = _desc()
    assert "the plan already has this" in desc
    assert "rather than reporting it as a gap" in desc


def test_the_warnings_that_were_already_right_survive():
    """The unavailable warning is the sharpest sentence in this description — it exists to stop
    an agent asking an author to re-supply what they already wrote. A correction must not
    displace it."""
    desc = _desc()
    assert "do NOT turn these into questions" in desc
    assert "they are candidates, not answers" in desc


def test_the_service_still_produces_the_fourth_bucket():
    """If `recovered` is ever dropped from the payload, the description becomes wrong in the
    other direction."""
    svc = (SRC.parents[1] / "services" / "plan_forge_service.py").read_text(encoding="utf-8")
    assert '"recovered": board["recovered"]' in svc
