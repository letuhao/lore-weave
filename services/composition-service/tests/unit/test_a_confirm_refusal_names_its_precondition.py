"""A caller can only respond to a refusal that names its precondition.

composition's confirm route answered `{"code": "action_error"}` with NO detail, while the
IMMEDIATE-path siblings say exactly what is wrong — "pause requires status=running, run is
draft". The confirm path was strictly worse than the direct one for the same failure.

🔴 THE SPLIT IS THE WHOLE POINT, AND I GOT IT WRONG FIRST. My initial sweep also named every
LookupError, reasoning "the caller already passed the book gate, so a not-found leaks nothing".
An existing guard — test_the_anti_oracle_denials_stay_bare — refuted that: "not-found and
not-permitted must stay UNIFORM". If a missing thing answers differently from a forbidden thing,
the PAIR of answers is the oracle, whatever either says alone. The guard was right; the sweep was
corrected rather than the guard relaxed.

🔴 AND THE MECHANICAL SWEEP ITSELF WAS UNSAFE. Rewriting 40 handlers by text produced TEN sites
where `exc` was not in scope — `UnboundLocalError` at runtime, caught only because the suite ran.
The whole sweep was reverted to HEAD and replaced by this narrow, verified change. A text
transform over exception handling cannot see scope, and this file's handlers come in several
shapes.

WHAT IS FIXED HERE: one site in composition.authoring_run_gate is genuinely nameable — an
upstream BookClientError. What is NOT fixed is the other ~50 bare sites across this file; that is
recorded on the ledger row, not silently widened.

🔴 THE PAYLOAD SITE WAS "FIXED" ONCE AND THEN CORRECTED, 2026-08-28. It was first named on the
reasoning "the caller minted the token and supplied the field, so naming it discloses nothing it
did not already have." That reasoning does not survive reading BOTH live mint sites —
composition_authoring_run_gate (legacy) and composition_authoring_run_manage's op=gate, its only
successor, which delegates to the identical function — both validate run_id with `_uuid()` before
minting. The branch is PROVABLY UNREACHABLE by any legitimate caller; a malformed value can only
mean a forged or corrupted token, which `_verify`'s own ConfirmTokenInvalid -> bare 400 mapping
already exists for. Detail helps a legitimate caller act; here there is none, and detail on a
forged token helps only the forger. It now re-raises ConfirmTokenInvalid and joins the bare set,
via a nested try so the AST gate — which only inspects handlers that call HTTPException directly
— correctly stops treating this site as nameable, without weakening the gate for the other sites.
"""
from __future__ import annotations

import pathlib

from app.routers import actions

SRC = pathlib.Path(actions.__file__).read_text(encoding="utf-8")
GATE = SRC[SRC.index("async def _execute_authoring_run_gate"):][:4500]


def test_the_payload_parse_is_PROVABLY_UNREACHABLE_and_stays_bare():
    """Confirmed by reading every mint site, not asserted: both composition_authoring_run_gate
    and composition_authoring_run_manage's op=gate (its only live successor) validate run_id with
    `_uuid()` before minting, so a malformed value can only come from a forged/corrupted token —
    which is `_verify`'s ConfirmTokenInvalid, already bare, reused here rather than named."""
    seg = GATE[GATE.index("except (KeyError, ValueError, TypeError) as exc:"):][:1300]
    assert "raise ConfirmTokenInvalid" in seg
    assert '"detail": str(exc)' not in seg
    # And the OUTER conversion, mirroring `_verify`'s own established mapping exactly.
    outer = GATE[GATE.index("except ConfirmTokenInvalid as exc:"):][:250]
    assert '{"code": "action_error"}' in outer
    assert '"detail": str(exc)' not in outer


def test_both_live_mint_sites_validate_run_id_before_minting():
    """The claim the correction rests on, pinned against the SOURCE rather than trusted from a
    docstring — if a future change lets either mint site skip validation, this goes red before
    the payload branch's bare answer becomes a real information gap."""
    mcp_src = pathlib.Path(actions.__file__).parent.parent.joinpath(
        "mcp", "server.py").read_text(encoding="utf-8")
    gate_fn = mcp_src[mcp_src.index("async def composition_authoring_run_gate"):][:900]
    assert 'run_id = _uuid(args.run_id, "run_id")' in gate_fn, (
        "composition_authoring_run_gate no longer validates run_id before minting — the payload "
        "branch this test's sibling covers may be reachable again"
    )
    # op=gate delegates to the SAME function (no separate mint path to check).
    manage_fn = mcp_src[mcp_src.index('if args.op == "gate":'):][:250]
    assert "composition_authoring_run_gate(" in manage_fn, (
        "op=gate no longer delegates to composition_authoring_run_gate — verify its own mint "
        "site validates run_id before trusting the payload branch stays unreachable"
    )


def test_the_upstream_failure_is_distinguishable_from_a_rejected_request():
    """A 502 the caller can retry versus a 400 it cannot: with both bare, they were the same
    answer with a different number."""
    seg = GATE[GATE.index("except BookClientError as exc:"):][:700]
    assert '"detail": str(exc)' in seg


def test_the_LOOKUP_failure_stays_UNIFORM():
    """The correction. not-found must answer exactly as not-permitted does, or the pair is an
    existence oracle — the position test_the_anti_oracle_denials_stay_bare already defends."""
    seg = GATE[GATE.index("except LookupError as exc:"):][:300]
    assert '{"code": "action_error"}' in seg
    assert '"detail": str(exc)' not in seg


def test_the_transition_reason_that_already_worked_is_untouched():
    """TOOLV2 LOOP #170 shipped this one. My reverted sweep briefly broke it, and its own guard
    caught that — pinned here too so a future edit to this effect cannot quietly undo it."""
    seg = GATE[GATE.index("except TransitionConflictError as exc:"):][:900]
    assert '"detail": str(exc)' in seg


# ── the file-wide gate ────────────────────────────────────────────────────────────────────────
# The per-handler tests above pin the instance this row was filed from. This one is the CLASS,
# and it is AST-based on purpose: my first attempt at the sweep was a text transform, and text
# cannot see scope. It produced ten sites where `exc` was unbound (UnboundLocalError at runtime)
# and then, "repairing" that, broke an existing guarantee by mis-reading the multi-line raise
# form. Both were caught by the suite rather than by review.

_NAMEABLE = frozenset({"KeyError", "ValueError", "TypeError", "InvalidOperation",
                       "BookClientError"})
#: LookupError is HERE, not above — see test_the_LOOKUP_failure_stays_UNIFORM.
_OPAQUE = frozenset({"OwnershipError", "InsufficientGrant", "ConfirmTokenInvalid", "LookupError"})


def _bare_action_errors():
    """Every `action_error` raise that is lexically INSIDE an `except … as exc` whose types are
    all nameable, and that still carries no reason. AST, so `exc` really is in scope."""
    import ast

    tree = ast.parse(SRC)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or not node.name:
            continue
        tp = node.type
        parts = tp.elts if isinstance(tp, ast.Tuple) else ([tp] if tp else [])
        names = {n.id for n in parts if isinstance(n, ast.Name)}
        if not names or (names & _OPAQUE) or not names <= _NAMEABLE:
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Raise) or sub.exc is None:
                continue
            call = sub.exc
            if not (isinstance(call, ast.Call)
                    and getattr(call.func, "id", "") == "HTTPException"):
                continue
            for kw in call.keywords:
                if kw.arg == "detail" and isinstance(kw.value, ast.Dict):
                    keys = {k.value for k in kw.value.keys if isinstance(k, ast.Constant)}
                    if keys == {"code"}:
                        out.append((sub.lineno, sorted(names)))
    return out


def test_no_NAMEABLE_failure_in_this_file_is_silent():
    """The class, enforced. A new handler that swallows its reason fails here rather than being
    discovered by a model that cannot act on the refusal."""
    bare = _bare_action_errors()
    assert not bare, (
        "these refusals name a precondition the caller could act on and say nothing: "
        + "; ".join(f"line {ln} (except {'/'.join(n)})" for ln, n in bare)
    )
