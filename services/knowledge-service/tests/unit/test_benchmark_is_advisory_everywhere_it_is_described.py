"""TOOLV2 LOOP #247 — the cost card promised a safety gate that was removed three weeks earlier.

Measured live, on a project whose embedding model had NO benchmark run at all:

    GET  /v1/kg/actions/preview  -> preview_rows included
                                    {"label": "⚠ benchmark", "value": "not passing",
                                     "note": "... confirm will be rejected otherwise"}
    POST /v1/kg/actions/confirm  -> 200 {"started": true, "job_id": "019ff1de-…",
                                         "status": "running", "scope": "all"}

The confirm was not rejected. The K17.9 benchmark stopped being a gate on 2026-07-27 — the
demotion is deliberate and its evidence is recorded at the check itself (the gate had blocked
every extraction on this instance for three months; the golden set is 20 English queries over a
synthetic fixture; it has a documented false-positive history). Nothing about that decision is in
question here. What was left behind is every sentence describing it.

The worst two are not comments:

  * the PREVIEW ROW is the cost card — the surface a human reads while deciding to spend money.
    It told them a gate stood between them and the spend. None did.
  * `kg_run_benchmark`'s tool description told the MODEL "Build-KG (kg_build_graph) is BLOCKED
    until this passes". A model that believes it will run a benchmark it does not need, or refuse
    a build it could have started, on a project where the benchmark may never pass at all.

This is the inverse of #144/#163/#210/#219, where a description over-promised what a tool would
do. Here it over-promises what the system will REFUSE to do — a false safety claim, which is the
more expensive direction to be wrong in.
"""

from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"


def _read(rel: str) -> str:
    return APP.joinpath(rel).read_text(encoding="utf-8").replace("\r\n", "\n")


def test_the_cost_card_does_not_claim_the_confirm_will_be_rejected():
    """The one a human reads before spending."""
    body = _read("ontology/build_graph_effect.py")
    assert "confirm will be rejected" not in body, (
        "the preview row promises a rejection again; measured, the confirm returned 200 started"
    )
    assert "the build will still run" in body, (
        "dropping the false claim is not enough — the row must say what actually happens, or a "
        "human reads a bare warning and infers the block anyway"
    )
    assert "advisory" in body


def test_the_benchmark_warning_row_still_exists():
    """The fix must not delete the signal. An unverified embedding model is worth telling someone
    who is about to pay for extraction — the defect was the CONSEQUENCE it claimed, not the row."""
    body = _read("ontology/build_graph_effect.py")
    assert '"label": "⚠ benchmark", "value": "not passing"' in body
    assert "benchmark_ok" in body, "the preview must still compute and return the flag"


def test_kg_run_benchmark_does_not_tell_the_model_that_build_is_blocked():
    """Three copies of this description exist (the OpenAI-schema list, the live MCP
    registration, and the handler docstring) and the first census found only two — 'enables'
    does not match a grep for 'enabled'. Assert over all three by name."""
    for rel in ("tools/definitions.py", "mcp/server.py", "tools/build_tools.py"):
        body = _read(rel)
        assert "is BLOCKED until this passes" not in body, f"{rel}: the false precondition is back"
        assert "enables Build-KG" not in body, (
            f"{rel}: 'a pass enables Build-KG' says the same thing in the positive direction"
        )


def test_the_no_embedding_model_refusal_does_not_sequence_the_benchmark_as_required():
    """The measured refusal — the only instruction a tool-calling model gets on that path — read
    '… then kg_run_benchmark, then retry this build'. A model following it runs a benchmark that
    can never be required, and on a model that fails the golden set it may never retry at all."""
    body = _read("tools/build_tools.py")
    assert "then kg_run_benchmark, then retry" not in body
    assert "That is the ONLY " in body, (
        "the refusal must say which precondition is real, not merely omit the false one"
    )


def test_no_description_sends_the_model_through_the_benchmark_as_a_required_step():
    """kg_build's own description and set_embedding_model's follow-up note both sequenced
    kg_run_benchmark as a required next step ('then kg_run_benchmark first', '(required, cheap)').
    The only hard precondition for target=graph is a configured embedding model."""
    for rel in ("tools/definitions.py", "mcp/server.py"):
        body = _read(rel)
        assert "then kg_run_benchmark first" not in body, f"{rel}: sequenced as required again"
    note = _read("tools/project_tools.py")
    assert "kg_run_benchmark (required" not in note, "set_embedding_model calls it required again"
    assert "OPTIONAL" in note


def test_the_start_core_really_has_no_benchmark_raise():
    """If the gate ever comes BACK, these descriptions become the false ones in the other
    direction and every assertion above would be pinning a new lie. Anchor them to the code."""
    body = _read("routers/public/extraction.py")
    start = body.index("# 2.5. K17.9 benchmark")
    end = body.index("# 2.6.", start)
    section = body[start:end]
    assert "raise HTTPException" not in section, (
        "the benchmark gate has been restored — the advisory wording shipped with #247 is now "
        "wrong and must be re-decided, not left to drift the other way"
    )
    assert "logger.info" in section and "logger.warning" in section, (
        "the demotion kept the result observable on the way past; a silent skip would make an "
        "un-benchmarked model invisible"
    )


def test_the_docstrings_do_not_list_a_benchmark_409_among_propagated_errors():
    """Two docstrings enumerated the HTTPExceptions the confirm route forwards and led with a
    benchmark 409 that cannot be raised — a maintainer reading either would keep the fiction."""
    for rel in ("ontology/build_graph_effect.py", "routers/public/kg_actions.py"):
        body = _read(rel)
        assert "benchmark gate 409" not in body, rel
        assert "K17.9 benchmark 409" not in body, rel
