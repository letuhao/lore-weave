"""A REQUIRED opaque id with no declared EMITTER is a tool the model cannot finish.

THE INVARIANT: every required, non-ambient `*_id` / `*_ref` argument must declare WHICH TOOL
emits it, in `contracts/agent-runtime-tool-contracts.json`'s `argument_emitters` map.

WHY THIS MAP AND NOT A PROSE DESCRIPTION. The platform already reads it in two places, so a
declaration here is not documentation — it changes behaviour twice:

  * `stream_service._missing_args_message` turns the generic *"establish that context first"*
    into *"Call `plan_propose_spec` first, then call this with the id it returns."*
  * R1 answerability is TRANSITIVE over this map, so declaring an emitter also puts that emitter
    on the wire — the model cannot walk to a supplier it was never shown.

A description that names a supplier in prose does neither. `declared_supplier`'s own docstring
gives the reason: *"the prose after the dash is for a human, and behaviour must not be decided
by it."*

🔴 MEASURED 2026-08-25, and it is why this gate exists rather than a lint over descriptions.
Of the 285 required non-ambient opaque ids across the 315-tool catalogue, **274 (96%) declare no
emitter**. The mechanism was built on 2026-08-23, wired into R1 the same day, and then left with
eleven entries — so for 96% of the ids the refusal still says nothing and R1 still forces nothing.
The ledger row that says the map "holds THREE real entries" is itself stale; it holds eleven.

🔴 AND THE REMEDIATION IS SMALLER THAN THE NUMBER LOOKS. The 274 gaps carry only **41 distinct
argument names**, because the same id recurs across a family: `book_id` on 84 tools, `project_id`
on 36, `chapter_id` on 23, `run_id` on 23. One verified decision covers a whole row.

🔴 THIS GATE IS BLIND TO 18 TOOLS, AND THE BLINDNESS IS THE SAME ONE THE RUNTIME HAD.
A flat-superset op-dispatch tool declares only `op` as required, because one schema serves several
ops — so `composition_motif_link_edit.from_motif_id` is OPTIONAL in the schema and never enters
this gate's population, even though `op=create` genuinely requires it and the server refuses
without it. The debt this file reports therefore UNDER-COUNTS by whatever those 18 tools' per-op
requirements are, and re-freezing after declaring one of them does not move the number.

Discovered 2026-08-25, the cycle after this gate shipped, while fixing
D-A-PER-OP-REFUSAL-NAMES-ARGUMENTS-AND-NO-MOVE. Stated here rather than quietly widened: the
per-op requirement lives in the server's `raise ValueError("op=create requires …")` and in the
tool's prose, not in the schema, so reading it would mean parsing one of those — a different
instrument with its own precision problem, not a tweak to this one.

🔴 WHY A BASELINE RATHER THAN A FLAT BAN — the same reason the sibling gate
(`test_required_args_are_declared_gate.py`) gives, and it is not laziness. An emitter declaration
is a claim that a specific tool RETURNS that id, and the registry's own standard for entering one
is "verified by calling it, not read from a description". Inventing 274 of those from names would
put the wrong tool on the wire for every matching turn — worse than the gap, because a model that
walks to a supplier which cannot supply is a model that has been actively misled. So the list is
FROZEN and may only SHRINK.
"""
from __future__ import annotations

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = ROOT / "contracts" / "tool-catalog-cache.json"
REGISTRY = ROOT / "contracts" / "agent-runtime-tool-contracts.json"
BASELINE = ROOT / "contracts" / "undeclared-emitter-baseline.json"


#: The three ids the RUNTIME backfills on every tool call — `stream_service._fill_context_args`
#: loops over exactly `("book_id", chapter_id", "project_id")`. They are never the model's to
#: obtain, so they can have no emitting TOOL, and the contract already says so in its own words:
#: `declared_supplier` classifies `book_read.book_id` as **context**, with the measurement that
#: made it worth building — *"book_read missing book_id — 78 calls over 46 sessions — and book_id
#: is a context value: the runtime fills it from the ambient book and simply has none outside a
#: book studio."*
#:
#: 🔴 THIS EXCLUSION WAS LEARNED THE HARD WAY, 2026-08-25, and the repo's own tests taught it.
#: A first pass declared `book_id <- book_list`, `chapter_id <- book_list` and
#: `project_id <- composition_list_derivatives` across 143 tools. Four chat-service tests went
#: red, and every one of them was right:
#:   * `book_read`'s refusal stopped saying *"NOT yours to invent: the runtime supplies it"* and
#:     started saying *"Call book_list first"* — reversing a deliberate design position.
#:   * `composition_list_outline.project_id` had NO emitter ON PURPOSE. stream_service records
#:     that dropping a cross-wired project_id there made the failure WORSE (the run looped on the
#:     repeat-breaker), and the drop is gated on an emitter existing. Declaring one re-armed it.
#: A shared spelling is not a shared obligation: these three are owed by the runtime.
_RUNTIME_CONTEXT_IDS = ("book_id", "chapter_id", "project_id")


#: {tool: (args,)} the SERVER fills, so no tool emits them and no emitter can be declared.
#: One entry, added 2026-08-30 with its reason at the check below. This set may only grow by a
#: decision with a reason recorded beside it.
_SERVER_FILLED_REFS = {
    "glossary_extract_entities_from_doc": ("source_ref",),
}


def _required_opaque_ids(spec: dict) -> list[str]:
    """The required arguments the MODEL must supply that are opaque ids.

    Ambient arguments are excluded on the tool's OWN declaration, never on the argument's name —
    only `_meta` knows which tool resolves `book_id` from the envelope. The runtime-context ids
    are excluded unconditionally, for the reason above.
    """
    schema = spec.get("inputSchema") or {}
    meta = spec.get("meta") or {}
    out = []
    for arg in sorted(set(schema.get("required") or [])):
        if not (arg.endswith("_id") or arg.endswith("_ref")):
            continue
        if arg in _RUNTIME_CONTEXT_IDS:
            continue
        if arg == "book_id" and meta.get("ambient_book"):
            continue
        if arg == "project_id" and meta.get("ambient_project"):
            continue
        # 🔴 A SERVER-FILLED REFERENCE IS NOT AN OPAQUE ID, and it is exempt for the same reason
        # the runtime-context ids above are: no tool emits it, so demanding an emitter would
        # demand a supplier that must not exist.
        #
        # SURFACED 2026-08-30 by refreshing contracts/tool-catalog-cache.json, which had gone
        # stale on 17 tools. `glossary_extract_entities_from_doc.source_ref` became REQUIRED under
        # DQ-T55 (owner: the author's document is not the model's to write), and its only accepted
        # value is the literal "last_user_message" — the server resolves it and fills
        # `source_markdown` before dispatch. Declaring an emitter would put a nonexistent supplier
        # on the wire for every extraction turn.
        #
        # NAMED, not inferred, and deliberately ONE entry: the gate's whole value is that it
        # refuses to guess which ids are obtainable, so this set may only grow by a decision with
        # a reason beside it — never because a flag was inconvenient.
        if arg in _SERVER_FILLED_REFS.get(spec.get("name") or "", ()):
            continue
        out.append(arg)
    return out


def _emitters() -> dict[str, dict]:
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    block = reg.get("argument_emitters") or {}
    # The map interleaves `_added_*` prose notes with real rows; only dict values are rows.
    return {k: v for k, v in block.items() if isinstance(v, dict)}


def _live_gaps() -> dict[str, list[str]]:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    emitters = _emitters()
    gaps: dict[str, list[str]] = {}
    for tool, spec in catalog.items():
        missing = [a for a in _required_opaque_ids({**spec, "name": tool})
                   if not (emitters.get(tool) or {}).get(a)]
        if missing:
            gaps[tool] = missing
    return gaps


@pytest.fixture(scope="module")
def baseline() -> dict[str, list[str]]:
    if not BASELINE.exists():
        pytest.skip(f"{BASELINE.name} not written yet")
    return json.loads(BASELINE.read_text(encoding="utf-8"))["tools"]


@pytest.fixture(scope="module")
def live() -> dict[str, list[str]]:
    if not CATALOG.exists():
        pytest.skip("catalogue cache unavailable in this checkout")
    return _live_gaps()


class TestTheListMayOnlyShrink:
    def test_no_NEW_tool_ships_a_required_id_with_no_emitter(self, live, baseline):
        new = {t: a for t, a in live.items() if t not in baseline}
        assert not new, (
            f"{len(new)} tool(s) ship a REQUIRED opaque id that declares no emitter: {new}. "
            "The model is told the id is mandatory, the refusal cannot name where to get it, and "
            "R1 cannot put the supplier on the wire. Add the emitter to argument_emitters in "
            "contracts/agent-runtime-tool-contracts.json — and VERIFY the supplier returns that "
            "id by calling it, never by reading a description.")

    def test_no_EXISTING_tool_gains_another(self, live, baseline):
        worse = {t: sorted(set(a) - set(baseline[t])) for t, a in live.items()
                 if t in baseline and set(a) - set(baseline[t])}
        assert not worse, f"already-listed tool(s) gained MORE undeclared ids: {worse}"

    def test_the_baseline_is_not_stale(self, live, baseline):
        """An id that HAS gained an emitter must leave the baseline.

        Without this the list rots upward: a declaration gets added, the debt number stays the
        same, and the baseline stops measuring anything. It is also the falsifier for every
        declaration this cycle adds — each one turns this test RED until the entry is removed.
        """
        fixed = {t: sorted(set(a) - set(live.get(t, []))) for t, a in baseline.items()
                 if set(a) - set(live.get(t, []))}
        assert not fixed, (
            f"these declare an emitter now and must come OUT of the baseline: {fixed}. "
            f"Re-freeze with the snippet in {BASELINE.name}.")


class TestTheDeclarationsThatWereMeasuredStayDeclared:
    """Each of these was added after a LIVE run showed the tool could not be completed without it.

    Named individually rather than trusted to the count: a baseline can shrink for the wrong
    reason (a tool leaving the catalogue), and these are the entries whose removal would silently
    re-break a turn that is known to have worked.
    """

    @pytest.mark.parametrize(("tool", "arg", "emitter"), [
        ("composition_generate", "model_ref", "settings_list_models"),
        ("composition_build_cast_and_graph", "model_ref", "settings_list_models"),
        ("composition_motif_adopt", "motif_id", "composition_motif_search"),
        ("glossary_create_evidence", "attr_value_id", "glossary_get_entity"),
        ("composition_arc_apply", "arc_template_id", "composition_arc_template_list"),
        ("plan_bootstrap_apply", "proposal_id", "plan_bootstrap_propose"),
        ("jobs_cancel", "job_id", "jobs_list"),
        ("jobs_get", "job_id", "jobs_list"),
        ("jobs_pause", "job_id", "jobs_list"),
        ("kg_build", "project_id", "kg_project_list"),
    ])
    def test_the_emitter_is_still_declared(self, tool, arg, emitter):
        got = (_emitters().get(tool) or {}).get(arg)
        assert got == emitter, (
            f"{tool}.{arg} should be emitted by {emitter!r}, got {got!r}. This entry was added "
            "after a measured live failure; removing it re-breaks that turn.")


class TestTheGateReadsTheRealMechanism:
    """The gate must fail for the reason the RUNTIME would, not for a lookalike of its own."""

    def test_it_agrees_with_declared_emitter(self):
        """`declared_emitter` is what stream_service actually calls. If this gate's reading of the
        map ever diverges from it, the gate is measuring a different thing than the platform."""
        import sys
        svc = ROOT / "services" / "chat-service"
        if not (svc / "app" / "agentruntime" / "toolcontract.py").exists():
            pytest.skip("chat-service not in this checkout")
        sys.path.insert(0, str(svc))
        try:
            from app.agentruntime.toolcontract import declared_emitter
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"toolcontract unimportable: {exc}")
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
        for tool, args in _emitters().items():
            for arg, emitter in args.items():
                assert declared_emitter(reg, tool, arg) == emitter, (
                    f"this gate and the runtime disagree about {tool}.{arg}")

    def test_a_runtime_context_id_is_never_asked_for_an_emitter(self):
        """book_id / chapter_id / project_id are backfilled by the runtime on every call, so no
        tool emits them and demanding one would be a permanent false positive — and, worse, an
        emitter on those re-arms a cross-wired DROP that was measured to make the failure worse."""
        spec = {"inputSchema": {"required": ["book_id", "chapter_id", "project_id", "map_id"]},
                "meta": {}}
        assert _required_opaque_ids(spec) == ["map_id"]

    def test_a_non_context_id_still_owes_one(self):
        spec = {"inputSchema": {"required": ["world_id"]}, "meta": {}}
        assert _required_opaque_ids(spec) == ["world_id"]

    def test_the_runtime_context_ids_match_what_the_runtime_actually_fills(self):
        """The exclusion is only honest while it mirrors `_fill_context_args`. If that loop gains
        or loses an id, this gate's population is wrong and nothing else would notice."""
        src = (ROOT / "services" / "chat-service" / "app" / "services" / "stream_service.py")
        if not src.exists():
            pytest.skip("chat-service not in this checkout")
        text = src.read_text(encoding="utf-8", errors="replace")
        needle = '("book_id", book_id), ("chapter_id", chapter_id), ("project_id", project_id)'
        assert needle in text, (
            "the runtime's context-fill loop no longer reads as this gate assumes — re-check "
            f"_RUNTIME_CONTEXT_IDS={_RUNTIME_CONTEXT_IDS} against it")

    def test_a_prose_note_in_the_map_is_not_read_as_a_tool(self):
        """The map interleaves `_added_*` strings with rows; a reader that treated one as a row
        would report a tool named `_added_2026_08_23` and quietly mis-count the debt."""
        assert not [k for k in _emitters() if k.startswith("_")]


class TestTheBaselineFileIsHonest:
    def test_counts_match_the_list(self, baseline):
        d = json.loads(BASELINE.read_text(encoding="utf-8"))
        assert d["count_tools"] == len(baseline)
        assert d["count_args"] == sum(len(a) for a in baseline.values())
