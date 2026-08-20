"""TOOLV2 LOOP #254 — the build card's benchmark warning could never turn off.

kg_run_benchmark does everything it claims. Measured live on a project configured with bge-m3:

    passed: true | recall_at_3: 1.0 | mrr: 1.0 | runs: 3 | gate_failures: []   in 3.3 seconds

"Cheap … runs immediately" holds. So does "a hidden sandbox (it never touches the real graph)":
the run was recorded under project 019ff246-…, whose name is `__benchmark__:019eeb08-…` — a
per-(user, model) sandbox project, not the caller's. The 10 :Passage nodes it created live in that
partition; no user project's counts moved.

Then the kg_build preview, on the same project, seconds later:

    benchmark_ok = False
    ⚠ benchmark | not passing

The warning is computed from `benchmark_repo.get_latest(owner, project.project_id,
embedding_model)` — PROJECT-scoped. The run exists under the SANDBOX project id. The two can never
meet, so no number of passing benchmarks could ever clear that row, on any project, for any user.

`get_latest_for_model` is the lookup written for precisely this case, and its docstring says so:
"the MODEL-scoped gate lookup … the benchmark answers 'is this *model* good enough?', which is a
per-model property, so a passing run on the user's hidden benchmark *sandbox* unlocks every
project using the same model." The extraction-start advisory already uses it. The card did not, so
the card and the core disagreed about the same fact.

This compounds #247. That iteration reworded this row because it falsely promised the confirm
would be rejected. The rewording was right and it was showing on 100% of previews — the row a
user could not make go away by doing the thing it asked for.
"""

from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
EFFECT = APP / "ontology" / "build_graph_effect.py"


def _body() -> str:
    return EFFECT.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_the_card_uses_the_model_scoped_lookup():
    body = _body()
    assert "get_latest_for_model(owner, project.embedding_model)" in body, (
        "the preview reads the benchmark project-scoped again; kg_run_benchmark records under a "
        "sandbox project, so that lookup can never match and the warning never clears"
    )
    assert "benchmark_repo.get_latest(owner, project.project_id" not in body, (
        "the project-scoped lookup is back"
    )


def test_the_reason_is_recorded_at_the_call_site():
    """Both lookups exist, differ by one word, and pick the wrong one silently — the next reader
    needs to know which is which without running a benchmark to find out."""
    body = _body()
    assert "MODEL-scoped, not project-scoped" in body
    assert "__benchmark__" in body, (
        "name the sandbox project convention; it is the fact that makes the project-scoped "
        "lookup wrong, and it is invisible from this file otherwise"
    )


def test_the_card_and_the_extraction_core_read_the_same_source():
    """The start core's advisory check has always been model-scoped. A card that disagrees with
    the core about the same fact is worse than either answer alone."""
    core = (APP / "routers" / "public" / "extraction.py").read_text(encoding="utf-8")
    assert "get_latest_for_model(" in core, (
        "the extraction core no longer uses the model-scoped lookup — the two paths must be "
        "re-aligned deliberately, not left to drift apart again"
    )


def test_the_model_scoped_lookup_still_drops_the_project_filter():
    """If get_latest_for_model ever grows a project filter it becomes get_latest, and this fix
    silently reverts while every assertion above still passes."""
    repo = (APP / "db" / "repositories" / "benchmark_runs.py").read_text(encoding="utf-8")
    start = repo.index("async def get_latest_for_model(")
    nxt = repo.find("\n    async def ", start + 10)  # it is currently the last method — find, not index
    fn = repo[start: nxt if nxt != -1 else len(repo)]
    assert "b.project_id =" not in fn, (
        "get_latest_for_model now filters on project_id — it no longer answers the per-model "
        "question the build card depends on"
    )
    assert "user_id" in fn, "cross-user isolation must survive dropping the project filter"


def test_the_warning_row_is_still_produced_when_it_is_genuinely_absent():
    """The fix must not make the row unreachable in the other direction — an un-benchmarked model
    is still worth telling someone who is about to spend."""
    body = _body()
    assert "if not benchmark_ok:" in body
    assert '"label": "⚠ benchmark", "value": "not passing"' in body
