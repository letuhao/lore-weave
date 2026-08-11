"""TOOLV2 LOOP #256 — a required input that its own named producer did not emit.

`kg_sync_apply` requires `base_source_hash`, and both its description and the repository's
docstring say where it comes from:

    tool:  "needs base_source_hash from kg_sync_available"
    repo:  "if the upstream source's current content_hash no longer equals `base_source_hash`
            (the token from /sync/available), raise SyncConflictError"

Measured live, that producer returns:

    {"adopted": true, "has_updates": false, "source_ref": "system:019feb06-…", "changes": []}

Four keys, no hash. `sync_diff` computes and returns `source_hash_current` and
`project_source_hash`, and the REST route `/sync/available` forwards both — the MCP projection
listed four keys by hand and dropped them. So the agent-native chain could not be completed at
all: the only producer the tool names cannot supply the value the tool demands.

This is #216's shape at its most severe. There the diagnostic was computed and discarded, and the
caller merely lost detail. Here the discarded value is a REQUIRED ARGUMENT of the next call, so
the tool is not degraded — it is unreachable, and an agent following the instructions exactly
still cannot get there.

The hash is emitted under the CONSUMER's name, `base_source_hash`, rather than the REST name.
sync_diff exposes two hashes and only one of them is the right one to pass; making an agent pick
correctly between `source_hash_current` and `project_source_hash` re-introduces the guess this fix
exists to remove.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "tools" / "graph_schema_tools.py"


def _handler() -> str:
    body = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = body.index("async def _handle_kg_sync_available(")
    return body[start: body.find("\nasync def ", start + 10)]


def test_the_producer_emits_the_hash_its_consumer_requires():
    fn = _handler()
    assert '"base_source_hash"' in fn, (
        "kg_sync_available no longer emits base_source_hash — kg_sync_apply requires it and "
        "names this tool as the source, so the chain breaks again"
    )
    assert 'diff.get("source_hash_current")' in fn, (
        "base_source_hash must carry the UPSTREAM current hash; that is the value sync_apply "
        "compares against"
    )


def test_it_is_not_wired_to_the_projects_own_frozen_hash():
    """sync_diff returns two hashes. `project_source_hash` is the copy frozen at adopt — passing
    that would 409 on every project that has upstream drift, i.e. exactly when sync is wanted."""
    fn = _handler()
    assert '"base_source_hash": diff.get("project_source_hash")' not in fn


def test_the_context_hash_is_available_too_but_under_its_own_name():
    fn = _handler()
    assert '"project_source_hash": diff.get("project_source_hash")' in fn


def test_the_unadopted_branch_is_left_alone():
    """A project that never adopted has no upstream and no hash to give. Emitting a null
    base_source_hash there would invite a call that cannot work; the branch returns early with
    adopted:false, which is the honest answer."""
    fn = _handler()
    assert '{"has_updates": False, "adopted": False, "changes": []}' in fn


def test_sync_apply_still_treats_the_hash_as_a_drift_guard():
    """If the comparison is ever dropped, emitting the hash becomes pointless and the tool
    silently loses its optimistic-concurrency check — a worse outcome than the missing field."""
    repo = (SRC.parents[1] / "db" / "repositories" / "ontology_mutations.py").read_text(
        encoding="utf-8"
    )
    assert "if current_hash != base_source_hash:" in repo
    assert "SyncConflictError" in repo
