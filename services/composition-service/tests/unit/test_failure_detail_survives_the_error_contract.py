"""TOOLV2 LOOP #216 — failure diagnostics were attached and then dropped on the wire.

composition_publish refuses an unpublishable chapter and deliberately attaches the gate, under a
comment that says so: "Surface the publish-gate up front so the LLM/user sees WHY if it isn't
publishable". Measured live, the caller received:

    {"message": "chapter is not publishable yet"}

and nothing else. The kit's C4 error body (loreweave_mcp.error_signal) is built from a
`{"success": False}` payload and forwards exactly three keys — message (from `error`), `code`, and
`detail`. Anything under another name never leaves the process.

An AST census of this module found FOUR failure payloads in that shape. (A regex first suggested 58;
that number was an artifact of a span that ran past the dict, and is recorded here only because the
difference is the point — the census had to be re-done properly before anything was believed.)

The worst of the four is the plan-pass refusal, whose own comment reads: "The agent gets the
BLOCKERS, not a bare failure — so its next move is 'accept the cast' rather than a blind retry that
will refuse identically forever." The blockers were exactly what got dropped, so the comment
described the opposite of what shipped, and the tool produced the blind-retry loop it was written to
prevent.

The fix is to ride `detail`, the one structured channel the contract already forwards. No kit change
and no contract change: the handlers were simply naming a key nobody reads.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py"
FORWARDED = {"success", "error", "code", "detail", "outcome"}


def _failure_payloads_dropping_keys() -> list[tuple[int, list[str]]]:
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    out: list[tuple[int, list[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Dict):
            continue
        pairs = list(zip(node.value.keys, node.value.values))
        keys = [k.value for k, _ in pairs if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        is_failure = any(
            isinstance(k, ast.Constant) and k.value == "success"
            and isinstance(v, ast.Constant) and v.value is False
            for k, v in pairs
        )
        if not is_failure or "outcome" in keys:
            continue
        dropped = [k for k in keys if k not in FORWARDED]
        if dropped:
            out.append((node.lineno, dropped))
    return out


def test_no_failure_payload_carries_detail_the_contract_would_drop():
    offenders = _failure_payloads_dropping_keys()
    assert offenders == [], (
        "these failure returns attach diagnostics under keys the C4 error body does not forward, "
        f"so the caller never sees them: {offenders}. Put the payload under `detail`."
    )


def test_the_publish_gate_rides_the_forwarded_channel():
    body = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert '"error": "chapter is not publishable yet",\n            "detail": gate,' in body, (
        "the publish gate is back under its own key and is dropped again"
    )


def test_the_plan_pass_blockers_ride_the_forwarded_channel():
    """The one whose comment promised the agent would get them."""
    body = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert '"detail": {"pass_id": exc.pass_id, "blockers": exc.blockers,' in body, (
        "blockers are dropped again — the refusal becomes a blind-retry loop, which is exactly "
        "what the comment above that return says it exists to prevent"
    )
