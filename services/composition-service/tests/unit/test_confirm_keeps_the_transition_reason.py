"""TOOLV2 LOOP #170 — the confirm path was strictly worse than the direct one.

Confirming a `composition.authoring_run_resume` token against a run in DRAFT correctly refused —
the run stayed draft — but answered:

    {"detail": {"code": "action_error"}}

with no reason at all. Its sibling on the immediate path, composition_authoring_run_pause, answers
"pause requires status=running, run is draft" for the same class of failure. So the cost-gated path,
the ONLY way to execute a W-tier action, told the caller less than the free one.

The reason was being caught and thrown away: `except TransitionConflictError as exc:` raised
`{"code": "action_error"}` and dropped `exc`, which carries the transition message. #164's gate
proves the mechanism supports detail — it returns "scope chapters not in this book: [...]".

Scope, deliberately narrow. 65 raise sites in this router drop the reason and 3 keep it, but most
of the 65 must stay bare: LookupError and (OwnershipError, InsufficientGrant) are the anti-oracle
denies, where a reason would confirm existence or access. TransitionConflictError is the one class
that cannot leak — a 409 means the caller already passed the book gate and the only fact added is
which state the run is in, which the direct-path tools already disclose.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "routers" / "actions.py"
BODY = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_every_transition_conflict_reports_its_reason():
    handlers = re.findall(
        r"except TransitionConflictError as exc:\n(.*?)from exc", BODY, re.S
    )
    assert len(handlers) == 5, f"expected 5 transition-conflict handlers, found {len(handlers)}"
    for h in handlers:
        assert '"detail": str(exc)' in h, (
            "a transition conflict is raised without its reason again — the confirm path goes back "
            "to saying less than the free immediate-path tools"
        )


def test_the_anti_oracle_denials_stay_bare():
    """The narrowness IS the fix. A sweep that also 'helped' these would turn a deliberate
    uniform deny into an existence oracle."""
    for guarded in ("except LookupError as exc:", "except (OwnershipError, InsufficientGrant) as exc:"):
        idx = BODY.find(guarded)
        assert idx != -1, f"{guarded} vanished — re-check this guard against the new shape"
        window = BODY[idx: idx + 400]
        assert '{"code": "action_error"}' in window, (
            f"{guarded} now leaks a reason; not-found and not-permitted must stay uniform"
        )


def test_a_reason_carrying_shape_already_existed_to_copy():
    """The mechanism was never the obstacle — three sites already did this."""
    assert BODY.count('"code": "action_error", "detail"') >= 3
