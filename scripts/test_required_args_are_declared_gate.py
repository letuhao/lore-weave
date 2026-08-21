"""A REQUIRED tool argument that declares nothing is an argument the model must GUESS.

MEASURED 2026-08-21 across the live federated catalogue: **502 of 1314 advertised properties (38%)
carry no description at all**, composition alone accounting for 451. Of those, **120 are REQUIRED
arguments across 68 tools** — the model is told a value is mandatory and told nothing about what it
is.

TWO DEFECTS IN THIS LOOP TRACE STRAIGHT TO IT, both measured live, both invisible until the
argument was declared:

  composition_generate.model_ref   {"title": "Model Ref", "type": "string"}
      -> the model sent "default" on 5/5 runs; the confirm effect does UUID(...), so approving
         produced a bare HTTP 400 on the most expensive tool on the platform.

  composition_motif_search.q       {"anyOf": [...], "default": null, "title": "Q"}
      -> asked to find a motif BY NAME, the model invented {"name": [...]} on 10/10 runs across
         two scenarios and got "Extra fields not permitted". The retry loop ended in a provider
         stream error, so composition_motif_edit and composition_motif_bind_edit both read
         "0/5 called, 5/5 errored" — which looked like a flaky rig for two batches.

Both tools COULD do what was asked. `q="Throwaway Loop"` returns the four matching motifs. The
capability was there; the declaration was not.

🔴 WHY A BASELINE RATHER THAN A FLAT BAN. Fixing all 120 means writing 120 honest descriptions,
and inventing text for an argument I have not read is exactly the kind of plausible-but-wrong
output this repo keeps paying for. So the list is FROZEN and may only SHRINK: a new undeclared
required argument fails this gate, and an entry that has been fixed also fails it, so the baseline
cannot quietly rot upward.

THE DECLARATION IS THE ARGUMENT'S, NOT THE TOOL'S. `composition_motif_search`'s description does
mention `q` in prose — "an exact name or code hit sorts first" — and the model still invented
`name`. Prose on the tool is not a declaration on the argument, and the argument is what gets
filled in.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASELINE = ROOT / "contracts" / "undeclared-required-args-baseline.json"
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))


def _live_offenders() -> dict[str, list[str]]:
    """{tool: [required args with no description]} from the catalogue cache."""
    import catalog  # noqa: PLC0415 — the cache reader lives beside the loop

    def _declares(prop: dict, defs: dict) -> bool:
        """Does the MODEL see a description for this argument?

        Not the same question as `prop["description"] is non-empty`, and reading it that way
        over-counted for a year of this baseline's life. An argument typed as a nested OBJECT
        arrives as a `$ref` with no description of its own, while the schema it points at
        carries one — plus a description on every field inside it. The model sees all of that;
        only a naive top-level read misses it.

        MEASURED 2026-08-22 across the whole 105-entry baseline: exactly ONE entry was this
        shape — `lore_enrichment_auto_enrich.args`, whose $ref target opens "Every field carries
        a Field(description=...) on purpose". One false positive in 105 is a sound instrument
        with a blind spot, not a broken one, but it is the same nesting trap that made
        kg_ontology_propose's enums look absent when they were nested inside an `anyOf` — and
        that one nearly bought a fix for a defect that did not exist.
        """
        if (prop.get("description") or "").strip():
            return True
        ref = prop.get("$ref") or next(
            (x.get("$ref") for x in (prop.get("anyOf") or []) if isinstance(x, dict) and x.get("$ref")),
            None)
        if not ref:
            return False
        target = defs.get(ref.rsplit("/", 1)[-1]) or {}
        return bool((target.get("description") or "").strip()
                    or any((f or {}).get("description") for f in (target.get("properties") or {}).values()))

    out: dict[str, list[str]] = {}
    for name, tool in catalog.load().items():
        schema = tool.get("inputSchema") or {}
        props = schema.get("properties") or {}
        defs = schema.get("$defs") or {}
        missing = sorted(
            arg for arg in (schema.get("required") or [])
            if not _declares(props.get(arg) or {}, defs)
        )
        if missing:
            out[name] = missing
    return out


@pytest.fixture(scope="module")
def baseline() -> dict[str, list[str]]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))["tools"]


@pytest.fixture(scope="module")
def live() -> dict[str, list[str]]:
    try:
        return _live_offenders()
    except Exception as exc:  # noqa: BLE001 — no catalogue cache in this checkout
        pytest.skip(f"catalogue unavailable: {exc}")


class TestTheListMayOnlyShrink:
    def test_no_NEW_tool_ships_an_undeclared_required_arg(self, live, baseline):
        new = {t: a for t, a in live.items() if t not in baseline}
        assert not new, (
            f"{len(new)} tool(s) gained a REQUIRED argument with no description: {new}. "
            "The model is told the value is mandatory and nothing about what it is — that is how "
            "model_ref became 'default' and q became 'name'. Describe it, and name its supplier "
            "if another tool produces it.")

    def test_no_EXISTING_tool_gains_another(self, live, baseline):
        worse = {t: sorted(set(a) - set(baseline[t])) for t, a in live.items()
                 if t in baseline and set(a) - set(baseline[t])}
        assert not worse, f"already-listed tool(s) gained MORE undeclared required args: {worse}"

    def test_the_baseline_is_not_stale(self, live, baseline):
        """An entry that has been fixed must be REMOVED, or the list rots upward and stops being a
        debt that shrinks."""
        fixed = {t: sorted(set(a) - set(live.get(t, []))) for t, a in baseline.items()
                 if set(a) - set(live.get(t, []))}
        assert not fixed, (
            f"these are declared now and must come OUT of the baseline: {fixed}. "
            f"Re-freeze with the snippet in {BASELINE.name}.")


class TestTheTwoMeasuredDefectsStayFixed:
    """Both are the reason this gate exists; neither may regress."""

    def test_composition_generate_model_ref_is_declared(self, live):
        assert "model_ref" not in live.get("composition_generate", []), (
            "model_ref lost its description — this is the argument the model filled with "
            "'default' on 5/5 runs, producing approve-then-fail")

    def test_composition_motif_search_q_is_declared(self, live):
        assert "q" not in live.get("composition_motif_search", []), (
            "q lost its description — this is the argument the model replaced with an invented "
            "`name` on 10/10 runs")

    def test_q_says_it_is_how_you_search_by_name(self):
        """The specific confusion that was measured: the model wanted a NAME search and could not
        see that `q` was it."""
        import catalog  # noqa: PLC0415

        try:
            props = (catalog.load()["composition_motif_search"].get("inputSchema") or {}).get(
                "properties") or {}
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"catalogue unavailable: {exc}")
        desc = (props.get("q") or {}).get("description", "").lower()
        assert "name" in desc, "q must say that searching by NAME is what it is for"


class TestTheBaselineFileIsHonest:
    def test_counts_match_the_list(self, baseline):
        d = json.loads(BASELINE.read_text(encoding="utf-8"))
        assert d["count_tools"] == len(baseline)
        assert d["count_args"] == sum(len(v) for v in baseline.values())

    def test_it_records_why_it_exists(self):
        note = json.loads(BASELINE.read_text(encoding="utf-8"))["_note"]
        assert "may only SHRINK" in note
        assert "model_ref" in note and "motif_search" in note
