"""Refreshing the catalogue from a DEGRADED surface silently poisons every later batch.

FOUND LIVE 2026-08-21, while committing a one-line description fix. The catalogue cache diff
was 33 insertions and 200 deletions - far more than the line I had changed. What had happened:

  * 14:34 - the cache was refreshed and committed. `memory_search`, `kg_build` and 24 other
            knowledge tools carried their synonyms. The live provider was serving them.
  * 15:47 - the infra-knowledge-service image was rebuilt. The new image contained NEITHER
            `surface="all"` (the author-search fix proven 0/5 -> 5/5 earlier in this loop) NOR
            any of the 26 `synonyms=` declarations committed on 08-14 and 08-21. The deployed
            app/mcp/server.py md5-matched a revision ELEVEN commits old.
  * every batch after that point ran against a surface where a whole provider had stopped
            declaring how to reach it.

Nothing failed. The service was healthy, all 315 tools still federated, every gate stayed
green. The regression was invisible because the only artifact that recorded it - the cache -
was OVERWRITTEN by the very command that observed it.

THE FIX IS THE REFUSAL, NOT THE DETECTION. `--refresh` now compares what it fetched against
what it is about to replace and refuses to write when a tool declares LESS than before. The
cache is this loop's ground truth: a batch measured against a degraded surface is not a weaker
measurement, it is a measurement of a platform that does not exist.

WHY ONLY LOSSES, AND WHY NOT DISAPPEARANCES. A tool that GAINS synonyms is progress and must
never block a refresh. A tool that vanishes entirely is normal provider churn and is already
owned by the deprecation sweep. What is never legitimate is a tool that is STILL ADVERTISED
while having quietly stopped saying what it is or how to ask for it.

RELATED, AND WHY THE IMAGE CHECK IS IN THE REFUSAL TEXT: this repo has paid for "verify the
deployed image matches source before diagnosing" more than once. A whole provider losing its
declarations at once is a deployment symptom, not a code symptom, so the refusal says which
command to run rather than leaving the reader to theorise.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import catalog  # noqa: E402


def _tool(desc="d", syn=None, props=("a",)):
    e = {"description": desc, "inputSchema": {"properties": {p: {} for p in props}}, "meta": {}}
    if syn:
        e["meta"]["synonyms"] = list(syn)
    return e


class TestItCatchesTheRegressionThatHappened:
    def test_a_provider_losing_its_synonyms_is_reported(self):
        old = {"memory_search": _tool(syn=["what do i know about"]),
               "kg_build": _tool(syn=["build the knowledge graph"]),
               "book_list": _tool(syn=["list books"])}
        new = {"memory_search": _tool(syn=None),
               "kg_build": _tool(syn=None),
               "book_list": _tool(syn=["list books"])}
        lost = catalog.surface_regressions(old, new)
        assert set(lost) == {"memory_search", "kg_build"}
        assert lost["memory_search"] == ["synonyms"]

    def test_a_lost_description_is_reported(self):
        lost = catalog.surface_regressions({"t": _tool(desc="real")}, {"t": _tool(desc="  ")})
        assert lost["t"] == ["description"]

    def test_an_emptied_input_schema_is_reported(self):
        """The de-federation shape: the tool is still listed, its arguments are gone."""
        lost = catalog.surface_regressions({"t": _tool(props=("a", "b"))}, {"t": _tool(props=())})
        assert lost["t"] == ["inputSchema.properties"]

    def test_the_report_names_the_provider_and_the_image_check(self):
        text = catalog._regression_report({"kg_build": ["synonyms"], "kg_view_read": ["synonyms"]})
        assert "kg=2" in text
        assert "md5sum" in text, "the refusal must say how to check the deployed image"
        assert "--allow-regression" in text, "and how to proceed if the loss is intended"


class TestItDoesNotFireOnProgressOrChurn:
    def test_gaining_synonyms_is_not_a_regression(self):
        assert catalog.surface_regressions({"t": _tool(syn=None)}, {"t": _tool(syn=["x"])}) == {}

    def test_an_unchanged_surface_is_clean(self):
        same = {"t": _tool(syn=["x"])}
        assert catalog.surface_regressions(same, dict(same)) == {}

    def test_a_retired_tool_is_not_a_regression(self):
        """Provider churn belongs to the deprecation sweep, not to this guard."""
        assert catalog.surface_regressions({"gone": _tool(syn=["x"])}, {}) == {}

    def test_a_brand_new_tool_is_not_a_regression(self):
        assert catalog.surface_regressions({}, {"new": _tool(syn=None)}) == {}


class TestTheGuardIsWiredIntoRefresh:
    def test_refresh_raises_rather_than_writing(self, tmp_path, monkeypatch):
        """The whole point: the degraded surface must NOT reach the cache file."""
        cache = tmp_path / "cache.json"
        cache.write_text('{"memory_search": {"description": "d", "inputSchema": {}, '
                         '"meta": {"synonyms": ["what do i know about"]}}}', encoding="utf-8")
        monkeypatch.setattr(catalog, "CACHE", cache)
        monkeypatch.setattr(catalog, "_fetch", lambda: _degraded())

        async def _degraded():
            return {"memory_search": {"description": "d", "inputSchema": {}, "meta": {}}}

        monkeypatch.setattr(catalog, "_fetch", _degraded)
        before = cache.read_text(encoding="utf-8")
        with pytest.raises(catalog.SurfaceRegressed) as exc:
            catalog._refresh_now()
        assert "memory_search" in str(exc.value)
        assert cache.read_text(encoding="utf-8") == before, "the cache was overwritten anyway"

    def test_allow_regression_writes_it(self, tmp_path, monkeypatch):
        cache = tmp_path / "cache.json"
        cache.write_text('{"memory_search": {"description": "d", "inputSchema": {}, '
                         '"meta": {"synonyms": ["x"]}}}', encoding="utf-8")
        monkeypatch.setattr(catalog, "CACHE", cache)

        async def _degraded():
            return {"memory_search": {"description": "d", "inputSchema": {}, "meta": {}}}

        monkeypatch.setattr(catalog, "_fetch", _degraded)
        catalog._refresh_now(allow_regression=True)
        assert "synonyms" not in cache.read_text(encoding="utf-8")
