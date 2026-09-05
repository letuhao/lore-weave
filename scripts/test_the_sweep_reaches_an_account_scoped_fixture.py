"""D-HARNESS-sweep-DOES-NOT-COVER-ACCOUNT-SCOPED-FIXTURES.

`Throwaway.teardown()` removes worlds, models, arc templates and motifs by the ids the object
watched come back, and it works — seven runs of scenarios-c-arcapply left zero rows.
`provision.py --sweep` is a FRESH PROCESS with no `self.seeded`, so it could only reach what a
NAME PREFIX finds: it reported "swept 1 throwaway book(s) / swept 1 throwaway world(s)" with the
seeded arc_template still sitting there, deleted by hand after a SELECT.

The gap is exactly the --keep-fixtures path, which is the INVESTIGATION path — the one taken
when something has already gone wrong and nobody is watching the store.

    THE INVARIANT. A sweep that cannot name what a run created must be told, not left to guess.

A PREFIX WOULD NOT DO, and this loop has paid for that lesson twice — `_purge_worlds` matched
nothing for 35 worlds. The seeds name themselves `emberfall-vein-b27-`,
`throwaway-loop-alpha-b19-`, `loop-arc-` and six other shapes with no common stem. Of the 57 arc
templates on this account 51 are account-scoped, and only ONE carries a code any prefix list
would match; the other 50 belong to earlier suites and must never be touched.

So the provenance is WRITTEN DOWN. Every seed step flushes a manifest under
scripts/toolloop/.fixtures/<run_id>.json; `teardown()` removes it, so a file left behind means a
fixture that was never torn down; `--sweep` replays each one through the fixture's OWN purge
methods. Flushed per step rather than at the end of build(), because a crash mid-build is
precisely when a sweep is needed.

MEASURED END TO END, 2026-08-27, against the live store:

    baseline                       57 arc templates on the account
    build + keep                   58, code loop-arc-89090824, book_id NULL
    the OLD sweep                  "swept 1 throwaway book(s)" -> still 58   <- the defect
    the manifest replay            deleted by id -> 57, exactly the baseline
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
import live_stack  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))
sys.path.insert(0, str(ROOT / "scripts"))

import provision as pr  # noqa: E402

# 🔴 THE OLD GUARD COULD NOT SKIP IN CI. `(ROOT / "infra").exists()` is true in every
# checkout (the directory is committed) and `docker ps` succeeds on every GitHub runner, so
# both proxies were TRUE where there is no stack at all. 22 red-ability proofs ran on the
# runner and failed with `could not read NEO4J_PASSWORD`, `SnapshotUnavailable`,
# `httpx.ConnectError` and `psql failed` -- every one of them saying only "no stack here".
# `live_stack.up()` probes the thing itself, via the anchor gate-wiring-gate already uses.
pytestmark = pytest.mark.skipif(not live_stack.up(), reason=live_stack.REASON)


def _sql(q: str) -> str:
    return subprocess.run(
        ["docker", "exec", "-i", "infra-postgres-1", "psql", "-U", "loreweave",
         "-d", "loreweave_composition", "-At", "-c", q],
        capture_output=True, text=True).stdout.strip()


def _templates() -> int:
    return int(_sql("SELECT count(*) FROM arc_template WHERE owner_user_id="
                    f"'{pr.OWNER_ID}';") or 0)


# ── the manifest itself ──────────────────────────────────────────────────────────────────

def test_a_seed_step_flushes_a_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(pr, "MANIFEST_DIR", tmp_path / ".fixtures")
    fx = pr.Throwaway("guard")
    fx.book_id = "book-1"
    fx._record({"tool": "composition_arc_template_create", "args": {}, "result": {"id": "t-1"}})
    data = json.loads(fx._manifest_path().read_text(encoding="utf-8"))
    assert data["book_id"] == "book-1"
    assert data["seeded"][0]["result"]["id"] == "t-1"
    assert data["run_id"] == fx.run_id


def test_every_seed_path_goes_through_the_recorder():
    """🔴 THE CALL SITE. A manifest written by three of the four seed kinds is a manifest that
    silently omits the fourth — and the omitted one would be the family that leaks."""
    src = (ROOT / "scripts" / "toolloop" / "provision.py").read_text(encoding="utf-8")
    assert src.count("self.seeded.append(") == 1, (
        "a seed path appends directly instead of going through _record, so its step never "
        "reaches the manifest"
    )
    at = src.index("self.seeded.append(")
    assert "_manifest_path().write_text" in src[at:at + 600], (
        "the one remaining append is not the recorder's — it appends without flushing"
    )
    assert src.count("self._record(") >= 4, "fewer recorder calls than there are seed kinds"


def test_teardown_removes_the_manifest_LAST(tmp_path, monkeypatch):
    """A manifest on disk means "never torn down", so removing it before the purges would erase
    the only record of what still needs removing."""
    monkeypatch.setattr(pr, "MANIFEST_DIR", tmp_path / ".fixtures")
    fx = pr.Throwaway("guard")
    fx._record({"sql": "x", "ok": True})
    assert fx._manifest_path().exists()
    fx.teardown()                      # no book, no seeds it can act on
    assert not fx._manifest_path().exists()
    src = (ROOT / "scripts" / "toolloop" / "provision.py").read_text(encoding="utf-8")
    body = src[src.index("def teardown(self)"):src.index("def _purge_models(self)")]
    assert body.index("purge_book(self.book_id)") < body.index("_manifest_path().unlink")
    assert body.count("return out") == 1, (
        "teardown has more than one exit — an early return skips the manifest removal, which "
        "is exactly the hole this guard found"
    )


def test_from_manifest_rebuilds_without_provisioning():
    fx = pr.Throwaway.from_manifest({"run_id": "abc123", "label": "l", "title": "T",
                                     "book_id": "b", "seeded": [{"tool": "x"}]})
    assert (fx.run_id, fx.book_id, fx.seeded) == ("abc123", "b", [{"tool": "x"}])


def test_the_sweep_REUSES_the_purge_methods():
    """Four families of DELETE, each with a hard-won guard in its docstring. A second copy in
    the sweep would be a second chance to get one wrong."""
    src = (ROOT / "scripts" / "toolloop" / "provision.py").read_text(encoding="utf-8")
    body = src[src.index("def sweep_manifests()"):src.index("def main()")]
    assert "fx.teardown()" in body, "the sweep does not go through the fixture's own teardown"
    assert "DELETE" not in body.upper().replace("DELETED", ""), (
        "the sweep writes its own DELETE — the purge logic must live in one place"
    )


def test_a_manifest_with_nothing_in_it_deletes_nothing(tmp_path, monkeypatch):
    """PRECISION. The purges act on ids the fixture RECORDED; an empty record must be a no-op,
    not a broadened predicate."""
    monkeypatch.setattr(pr, "MANIFEST_DIR", tmp_path / ".fixtures")
    (tmp_path / ".fixtures").mkdir(parents=True)
    (tmp_path / ".fixtures" / "empty.json").write_text(
        json.dumps({"run_id": "empty", "seeded": [], "book_id": None}), encoding="utf-8")
    before = _templates()
    out = pr.sweep_manifests()
    assert out["manifests"] == 1 and not out["errors"], out
    assert _templates() == before


def test_an_unreadable_manifest_is_REPORTED_not_fatal(tmp_path, monkeypatch):
    """The point of a sweep is that it runs when something has already gone wrong."""
    monkeypatch.setattr(pr, "MANIFEST_DIR", tmp_path / ".fixtures")
    (tmp_path / ".fixtures").mkdir(parents=True)
    (tmp_path / ".fixtures" / "broken.json").write_text("{not json", encoding="utf-8")
    (tmp_path / ".fixtures" / "ok.json").write_text(
        json.dumps({"run_id": "ok", "seeded": [], "book_id": None}), encoding="utf-8")
    out = pr.sweep_manifests()
    assert out["manifests"] == 2
    assert len(out["errors"]) == 1 and "broken.json" in out["errors"][0]
    assert len(out["purged"]) == 1, "one bad manifest ended the sweep"


def test_the_sweep_runs_manifests_BEFORE_the_book_sweep():
    """A manifest knows the fixture's book AND its account-scoped rows; deleting the book first
    pulls it out from under a purge that still needs it."""
    src = (ROOT / "scripts" / "toolloop" / "provision.py").read_text(encoding="utf-8")
    body = src[src.index("if a.sweep:"):]
    assert body.index("sweep_manifests()") < body.index("sweep_orphans()")


def test_the_manifest_dir_is_git_ignored():
    """Live state about THIS machine's runs, not a fact about the repo — and a committed
    manifest would make a later sweep try to delete another machine's rows."""
    ignored = subprocess.run(
        ["git", "check-ignore", "scripts/toolloop/.fixtures/x.json"],
        cwd=ROOT, capture_output=True, text=True)
    assert ignored.returncode == 0, "scripts/toolloop/.fixtures/ is not git-ignored"


# ── the defect, end to end, against the real store ───────────────────────────────────────

def test_the_OLD_sweep_leaves_it_and_the_REPLAY_removes_it():
    """🔴 THE WHOLE ROW, reproduced and then closed, on a fixture this test creates.

    Both halves matter. If only the second were asserted, a prefix sweep that happened to match
    would look identical — and the row exists because a name-based guard silently matched
    nothing for 35 worlds."""
    baseline = _templates()
    sc = json.loads((ROOT / "scripts" / "toolloop" / "scenarios-c-arcapply.json")
                    .read_text(encoding="utf-8"))["scenarios"][0]
    fx = pr.Throwaway("sweepguard")
    fx.build(sc.get("seed") or [], chapter=True)
    code = f"loop-arc-{fx.run_id}"
    try:
        assert fx._manifest_path().exists(), "the build wrote no manifest"
        assert _sql(f"SELECT count(*) FROM arc_template WHERE code='{code}';") == "1"

        # The defect: everything the old --sweep did, and the row survives it.
        pr.sweep_orphans()
        pr.sweep_orphan_worlds()
        assert _sql(f"SELECT count(*) FROM arc_template WHERE code='{code}';") == "1", (
            "the name-scoped sweeps now reach an account-scoped template — this test's premise "
            "is gone and the manifest may be unnecessary"
        )

        # The fix.
        out = pr.sweep_manifests()
        assert not out["errors"], out
        assert _sql(f"SELECT count(*) FROM arc_template WHERE code='{code}';") == "0"
        assert _templates() == baseline, (
            "the account did not return to its baseline — the sweep reached rows this run did "
            "not create, which is worse than the leak"
        )
        assert not fx._manifest_path().exists()
    finally:
        _sql(f"DELETE FROM arc_template WHERE code='{code}';")
        try:
            fx.teardown()
        except Exception:  # noqa: BLE001 — the assertions above are the test
            pass


# ── the fifth family, and the first outside Postgres ─────────────────────────────────────
#
# Found 2026-08-27 by leaking two. The idempotency probe's memory_remember facts are stored
# with project_id NULL, so the throwaway book's teardown could never see them, and only a
# Cypher read found them. `memory_forget` INVALIDATES rather than deletes, so the node would
# stay and carry the run's content into every later memory_search.

def test_a_seeded_MEMORY_FACT_is_purged_by_provenance():
    from eval.tool_liveness import oracle
    fx = pr.Throwaway("memguard")
    r = fx.mcp.call("memory_remember",
                    {"fact_text": "Provenance purge guard fact, harness only.",
                     "fact_type": "decision"})
    fid = r.get("fact_id")
    assert fid, r
    fx.seeded = [{"tool": "memory_remember", "args": {}, "result": r}]
    try:
        assert oracle.cypher_query(f"MATCH (f:Fact {{id:'{fid}'}}) RETURN count(f);")[0][0] == "1"
        assert fx._purge_memories() == [str(fid)]
        assert oracle.cypher_query(f"MATCH (f:Fact {{id:'{fid}'}}) RETURN count(f);")[0][0] == "0"
    finally:
        oracle.cypher_query(f"MATCH (f:Fact {{id:'{fid}'}}) DETACH DELETE f;")


def test_the_memory_purge_REFUSES_an_id_it_cannot_trust():
    """🔴 THE FIRST DRAFT ESCAPED NOTHING. `i.replace("'", "\'")` is `"'"` in Python — a no-op
    that reads as escaping and never fires, because a fact id is hex. A DETACH DELETE is not the
    place for a quoting scheme, so an id that is not id-shaped is refused."""
    fx = pr.Throwaway("memguard")
    fx.seeded = [{"tool": "memory_remember", "args": {},
                  "result": {"fact_id": "x' OR 1=1 --"}}]
    with pytest.raises(pr.ProvisionError, match="not id-shaped"):
        fx._purge_memories()


def test_teardown_runs_the_memory_purge():
    """A purge nothing calls is the leak by another route — the shape this loop keeps finding."""
    src = (ROOT / "scripts" / "toolloop" / "provision.py").read_text(encoding="utf-8")
    body = src[src.index("def teardown(self)"):src.index("def _purge_models(self)")]
    assert "self._purge_memories()" in body
