"""D-W10-ARC-CONFORMANCE-SUCCESSION (F2) — causal-edge inference.

Pure pieces (build_messages / parse_edges) + infer_causal_edges with a fake LLM (forward-only
guard, window dedupe, advisory degrade) + the two route mounts/auth.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.extraction.causal_edges import build_messages, infer_causal_edges, parse_edges

EVENTS = [
    {"id": "e1", "title": "Humiliation", "summary": "A public shaming."},
    {"id": "e2", "title": "Exile", "summary": ""},
    {"id": "e3", "title": "Face slap", "summary": "The retort."},
]
ORDER = {"e1": 0, "e2": 1, "e3": 2}
WIN = {"e1", "e2", "e3"}


def test_build_messages_labels_events_in_order():
    """This test used to assert the format that CAUSED the corpus bite to return
    zero: `1. id=e1` put a line number beside the id, and the model answered with
    the number — `[[1, 2, "causes"], …]` — so `parse_edges` dropped every triple.
    One handle per event, and it is the handle the answer is asked for."""
    user = build_messages(EVENTS)[1]["content"]
    assert "E1 | " in user and "E3 | " in user and "A public shaming." in user
    assert "1. id=" not in user, "a line number is a second handle to answer with"


def test_parse_edges_keeps_forward_drops_backward_self_and_foreign():
    # T33 widened the edge to (a, b, relation). The filtering asserted here is UNCHANGED —
    # forward-only, no self-loops, no invented ids — only the shape moved, so this keeps
    # covering what it always covered rather than being replaced by the new-shape tests.
    content = '[["e1","e3","causes"], ["e3","e1","causes"], ["e2","e2","causes"], ["e1","ghost","causes"]]'
    out = parse_edges(content, order_index=ORDER, window_ids=WIN)
    assert out == [("e1", "e3", "causes")]  # forward only; backward/self/foreign dropped


def test_parse_edges_tolerates_edges_wrapper_and_fence():
    content = '```json\n{"edges": [["e1","e2","causes"]]}\n```'
    assert parse_edges(content, order_index=ORDER, window_ids=WIN) == [("e1", "e2", "causes")]


def test_parse_edges_junk_is_empty():
    assert parse_edges("no json", order_index=ORDER, window_ids=WIN) == []


def _job(content, status="completed"):
    return SimpleNamespace(status=status, result={"messages": [{"content": content}]})


class _FakeLLM:
    def __init__(self, job=None, raises=False):
        self._job, self._raises = job, raises
        self.calls = 0
    async def submit_and_wait(self, **kw):
        self.calls += 1
        if self._raises:
            raise RuntimeError("down")
        return self._job


async def test_infer_returns_validated_forward_edges():
    llm = _FakeLLM(_job('[["e1","e2","causes"], ["e2","e3","precedes"]]'))
    out = await infer_causal_edges(llm, user_id="u", model_source="user_model",
                                   model_ref="m1", events=EVENTS)
    # T33: the relation now rides on the edge, and the two kinds are kept distinct all the way
    # out of the inference rather than being flattened at the boundary.
    assert out == [("e1", "e2", "causes"), ("e2", "e3", "precedes")]


async def test_infer_degrades_on_exception():
    llm = _FakeLLM(raises=True)
    assert await infer_causal_edges(llm, user_id="u", model_source="user_model",
                                    model_ref="m1", events=EVENTS) == []


async def test_infer_noops_under_two_events():
    llm = _FakeLLM(_job("[]"))
    assert await infer_causal_edges(llm, user_id="u", model_source="s", model_ref="m",
                                    events=EVENTS[:1]) == []
    assert llm.calls == 0


def test_causal_routes_are_registered():
    from app.main import app
    from loreweave_obs.routes import route_paths  # FastAPI 0.139: app.routes is not flat
    paths = route_paths(app)
    assert "/internal/extraction/causal-edges" in paths
    assert "/internal/extraction/causal-motif-pairs" in paths


def test_causal_edges_requires_internal_token():
    from fastapi.testclient import TestClient
    from app.main import app
    resp = TestClient(app, raise_server_exceptions=False).post(
        "/internal/extraction/causal-edges",
        json={"user_id": "00000000-0000-0000-0000-000000000000",
              "book_id": "00000000-0000-0000-0000-000000000000",
              "model_source": "user_model", "model_ref": "m1"})
    assert resp.status_code == 401


# ── T33g: one ordered pair, ONE relation ───────────────────────────────────────────────────
#
# Measured on the acceptance corpus 2026-08-30: the extractor wrote 134 edges across 124
# distinct ordered pairs — 10 pairs carried BOTH `CAUSES` and `PRECEDES`. The prompt asks for
# "exactly one of" and the model obeys; the duplication is structural. `_WINDOW` is 12 and
# `_STRIDE` is 6, so consecutive windows overlap by half and a pair in the overlap is judged
# twice, in two different contexts. `edges` is a set of TRIPLES, so both judgements survive.

from app.extraction.causal_edges import reconcile_relations


def test_two_windows_that_AGREE_leave_one_edge():
    kept, disagreed = reconcile_relations([("a", "b", "causes"), ("a", "b", "causes")])
    assert kept == [("a", "b", "causes")]
    assert disagreed == []


def test_two_windows_that_DISAGREE_keep_the_WEAKER_claim():
    """The module's own rule, not a new one: 'PREFER unknown over guessing: a wrong order is
    worse than an absent one.' Two windows that cannot agree on WHY have not established why;
    what they agree on is the ORDER."""
    kept, disagreed = reconcile_relations([("a", "b", "causes"), ("a", "b", "precedes")])
    assert kept == [("a", "b", "precedes")]
    assert disagreed == [("a", "b")]


def test_the_resolution_does_not_depend_on_which_window_came_first():
    """Set iteration order must not decide world order — the same reason `drop_cycles` is
    handed a sorted list."""
    one, _ = reconcile_relations([("a", "b", "causes"), ("a", "b", "precedes")])
    two, _ = reconcile_relations([("a", "b", "precedes"), ("a", "b", "causes")])
    assert one == two == [("a", "b", "precedes")]


def test_DIFFERENT_pairs_are_untouched():
    """The control: reconciling must not collapse edges that were never in conflict, or it
    would quietly delete the extractor's actual output."""
    kept, disagreed = reconcile_relations(
        [("a", "b", "causes"), ("b", "c", "precedes"), ("a", "c", "causes")])
    assert kept == [("a", "b", "causes"), ("a", "c", "causes"), ("b", "c", "precedes")]
    assert disagreed == []


def test_a_reversed_pair_is_a_DIFFERENT_pair():
    """(a,b) and (b,a) are distinct claims; only the cycle guard may refuse the second."""
    kept, disagreed = reconcile_relations([("a", "b", "causes"), ("b", "a", "precedes")])
    assert len(kept) == 2 and disagreed == []


class _ScriptedLLM:
    """Answers each window differently, which is what overlapping windows actually do."""

    def __init__(self, contents):
        self._contents = list(contents)
        self.calls = 0

    async def submit_and_wait(self, **kw):
        i = min(self.calls, len(self._contents) - 1)
        self.calls += 1
        return _job(self._contents[i])


async def test_infer_causal_edges_ACTUALLY_RECONCILES_a_disagreeing_pair():
    """THE WIRING, not the rule.

    `reconcile_relations` passing its own tests proves nothing about whether
    `infer_causal_edges` calls it — BITE T33g-2 proved exactly that: removing the call left
    all five pure-function tests green. A correct filter that nothing invokes is the shape
    this repo keeps finding.

    The overlap has to be REAL or the test measures nothing: `_WINDOW` is 12 and `_STRIDE`
    is 6, so window A is events[0:12] and window B is events[6:18]. Only a pair inside
    events[6:12] is judged twice. My first draft used three events, produced ONE window, and
    failed for that reason rather than the one it was written for.

    The E-labels are per-window, which is the point of `event_tokens`: the same pair is
    (E7,E8) in window A and (E1,E2) in window B.
    """
    events = [{"id": f"e{i}", "title": f"T{i}", "summary": ""} for i in range(1, 15)]
    llm = _ScriptedLLM(['[["E7","E8","causes"]]', '[["E1","E2","precedes"]]'])
    out = await infer_causal_edges(llm, user_id="u", model_source="user_model",
                                   model_ref="m1", events=events)
    assert llm.calls >= 2, "the windows must OVERLAP or nothing is judged twice"
    pairs = [(a, b) for a, b, _rel in out]
    assert len(pairs) == len(set(pairs)), f"one pair must carry ONE relation, got {out}"
    assert ("e7", "e8", "precedes") in out, f"the weaker claim must survive, got {out}"
    assert ("e7", "e8", "causes") not in out
