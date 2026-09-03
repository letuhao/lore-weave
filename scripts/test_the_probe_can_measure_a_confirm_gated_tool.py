"""D-IDEMPOTENCY-PROBE-CANNOT-MEASURE-A-CONFIRM-GATED-TOOL.

    THE INVARIANT. A Tier-W tool writes nothing until its token is redeemed, so a probe that
    calls twice and reads the store between is measuring two no-ops. It must call → redeem →
    call → redeem, and compare across the SECOND redemption.

Measured on composition_decompile_arcs, whose own scenario asks "decompiling a book that
ALREADY has an arc layer must not silently duplicate it" — a question that can only be asked
AFTER a first confirmation. Both diffs came back empty however the tool behaved, and the
probe's own guard correctly reported "two no-ops … proves nothing".

THE MECHANISM WAS ALREADY SHIPPED AND THE ROW WAS NEVER UPDATED. `_redeem_if_gated` exists and
is called at BOTH call sites. What was missing is this file: nothing kept it red-able, so it
could have been deleted and every suite would have stayed green — the third time this week that
the work turned out to be the guard rather than the mechanism.

LIVE, the tool the row was written from, K=5, throwaway fixture per run:

    first    ok: {"confirm_token": "eyJkIjoiY29tcG9zaXRpb24uZGVjb21waWxlIiwi…
    diff 1   outline_node rows 3 -> 3, latest 22:00:48 -> 22:01:05
    diff 2   outline_node rows 3 -> 3, latest 22:01:05 -> 22:01:26
    IDEMPOTENT IN EFFECT — no row was added or removed by the second call

and 5 of 5 reps agree exactly: diff_first and diff_second both non-empty, the redemption
recorded as `['query: 200']`, the verdict identical, zero errored and zero "proves nothing".

Both diffs non-empty is the whole point: the store moved, so the verdict is about the tool. And
the answer is the scenario's own question — 3 rows before, 3 after, no duplication.

TWO THINGS THE HELPER GOT RIGHT THAT A REWRITE WOULD LOSE, so they are pinned here:
  * THE PREFIX IS NOT THE DOMAIN. `kg_*` lives in `knowledge` and `plan_*` in `composition`.
  * THERE ARE TWO CONFIRM CONVENTIONS — a query param for composition/book/translation and a
    JSON body for knowledge, whose PATH segment is `kg`, not `knowledge`. Both are tried and
    every attempt is recorded, because the failing shape a caller happens to try last is not
    the diagnosis.
"""
from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))
sys.path.insert(0, str(ROOT / "scripts"))

import idempotency_probe as ip  # noqa: E402

SRC = (ROOT / "scripts" / "toolloop" / "idempotency_probe.py").read_text(encoding="utf-8")


def test_BOTH_calls_redeem():
    """🔴 THE CALL SITE, and redeeming only the first would be worse than redeeming neither: the
    first write would land, the second would not, and the probe would report a tool that
    "wrote once and then stopped" — a defect that did not happen."""
    tree = ast.parse(SRC)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "run_one")
    slots = [c.args[2].value for c in ast.walk(fn)
             if isinstance(c, ast.Call) and getattr(c.func, "id", None) == "_redeem_if_gated"]
    assert sorted(slots) == ["first", "second"], slots


def test_a_result_with_no_token_is_left_alone(monkeypatch):
    """PRECISION. A Tier-A tool writes immediately; posting a confirm for it would be a second
    write the probe invented."""
    calls = []
    monkeypatch.setattr(ip.httpx, "post", lambda *a, **k: calls.append(a) or None)
    out = {"tool": "jobs_pause"}
    ip._redeem_if_gated({"ok": True, "status": "paused"}, out, "first")
    ip._redeem_if_gated("not even a dict", out, "first")
    ip._redeem_if_gated({"confirm_token": ""}, out, "first")
    assert calls == [] and "confirm" not in out


def test_the_domain_is_MAPPED_not_split():
    """`kg_*` -> knowledge, `plan_*` -> composition. A bare prefix split looks up a base url for
    'kg' and finds none, and the probe then reports a tool that would not confirm."""
    assert ip._domain_of("kg_propose_edge") == "knowledge"
    assert ip._domain_of("plan_compile") == "composition"
    assert "_domain_of(out[\"tool\"])" in SRC, "the helper re-derives the domain by hand"


def test_BOTH_confirm_conventions_are_tried_and_kg_uses_the_kg_PATH():
    """Redeeming a kg token at /v1/knowledge/actions/confirm returns 404 — measured. The path
    segment is `kg`, and both the query and body shapes are attempted."""
    seen = []

    class R:
        status_code, text = 404, "nope"

    def fake_post(url, **kw):
        seen.append((url, "params" if "params" in kw else "body"))
        return R()

    orig = ip.httpx.post
    ip.httpx.post = fake_post
    try:
        out = {"tool": "kg_propose_edge"}
        ip._redeem_if_gated({"confirm_token": "tok"}, out, "first")
    finally:
        ip.httpx.post = orig
    assert seen, "nothing was attempted"
    assert all("/v1/kg/actions/confirm" in u for u, _ in seen), seen
    assert {s for _, s in seen} == {"params", "body"}, seen


def test_EVERY_attempt_is_recorded_not_just_the_last():
    """🔴 KEEPING ONLY THE LAST HID THE ANSWER. The query attempt returned 400 with the real
    reason, the body attempt then returned a meaningless 422, and the record said "422 body" —
    sending the reader after a validation problem that did not exist."""
    class R:
        def __init__(self, c):
            self.status_code, self.text = c, f"body-{c}"
    codes = iter([400, 422])
    orig = ip.httpx.post
    ip.httpx.post = lambda url, **kw: R(next(codes))
    try:
        out = {"tool": "composition_decompile_arcs"}
        ip._redeem_if_gated({"confirm_token": "tok"}, out, "first")
    finally:
        ip.httpx.post = orig
    tried = out["confirm"]["first"]
    assert len(tried) == 2, tried
    assert any("400" in t for t in tried) and any("422" in t for t in tried)


def test_a_SUCCESS_stops_after_the_shape_that_answered():
    class R:
        def __init__(self, c):
            self.status_code, self.text = c, ""
    orig = ip.httpx.post
    ip.httpx.post = lambda url, **kw: R(200)
    try:
        out = {"tool": "composition_decompile_arcs"}
        ip._redeem_if_gated({"confirm_token": "tok"}, out, "first")
    finally:
        ip.httpx.post = orig
    assert out["confirm"]["first"] == ["query: 200"], out


def test_a_transport_failure_is_RECORDED_never_swallowed():
    """A silent failure here looks exactly like a tool that wrote nothing, which is the defect
    this whole file is about arriving by another route."""
    orig = ip.httpx.post

    def boom(url, **kw):
        raise ConnectionError("down")
    ip.httpx.post = boom
    try:
        out = {"tool": "composition_decompile_arcs"}
        ip._redeem_if_gated({"confirm_token": "tok"}, out, "first")
    finally:
        ip.httpx.post = orig
    assert any("ConnectionError" in t for t in out["confirm"]["first"])


@pytest.mark.skipif(subprocess.run(["docker", "ps"], capture_output=True).returncode != 0,
                    reason="needs the local stack")
def test_LIVE_the_probe_produces_a_real_verdict_for_the_gated_tool(tmp_path):
    """ANTI-VACUITY that costs a fixture and is worth it: the row's claim is that BOTH diffs
    come back empty. This asserts they do not — a verdict built on two empty diffs is the
    defect, whatever words it uses."""
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps([{"tool": "composition_decompile_arcs",
                                 "args": {"book_id": "{book_id}"}}]), encoding="utf-8")
    scen = json.loads((ROOT / "scripts" / "toolloop" / "scenarios-idem-decompile.json")
                      .read_text(encoding="utf-8"))
    r = ip.run_one(scen, "composition_decompile_arcs", {"book_id": "{book_id}"})
    assert "error" not in r, r
    assert r["diff_first"], "the FIRST call still wrote nothing — the redemption did not land"
    assert r["diff_second"], "the SECOND call wrote nothing — the probe is measuring a no-op"
    assert "proves nothing" not in r["verdict"], r["verdict"]
    assert r.get("confirm", {}).get("first"), "no redemption was recorded for the first call"
