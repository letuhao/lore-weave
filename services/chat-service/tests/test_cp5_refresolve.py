"""CP-5.3 — identifier resolution: two branches, no guess, and a resolver that must be a read.

The pilot (§3b) cleared this row and also decided its shape: **ambiguity is measured, not
hypothetical** — 4 exact matches for `Dracula` tied at `rank_score` 0.9, 37.5% of contested calls —
so the refusal branch carries real traffic and a `rank_score` tiebreak would be a guess deciding a
correctness question.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from app.agentruntime.refresolve import (
    RefContractViolation, Resolver, apply_resolutions, decide, load_registry, looks_like_an_id,
    pending_for, refusal_message, resolve_call,
)

REGISTRY = (pathlib.Path(__file__).resolve().parents[3]
            / "contracts" / "agent-runtime-ref-resolvers.json")
BASELINE = (pathlib.Path(__file__).resolve().parents[3]
            / "contracts" / "agent-runtime-baseline" / "tools-list.snapshot.json")

BOOK = "019f6531-f4d9-7346-8f97-0b15c752fc39"


def registry_doc() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def catalogue() -> list[dict]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))["tools"]


def lane_of(tool: str) -> str | None:
    by_tier = {"R": "read", "A": "action", "W": "write", "S": "system"}
    for t in catalogue():
        fn = t.get("function", t)
        if fn.get("name") == tool:
            return by_tier.get((fn.get("_meta") or {}).get("tier"))
    return None


def loaded():
    return load_registry(registry_doc(), lane_of)


def hit(name: str, tier: str = "exact", eid: str = "019f0000-0000-7000-8000-000000000001"):
    return {"entity_id": eid, "cached_name": name, "tier": tier, "rank_score": 0.9}


class TestAResolverMustBeARead:
    """🔴 A SAFETY PROPERTY, NOT A PREFERENCE. Auto-resolution dispatches a tool the user never
    asked for; a non-read resolver would perform an unrequested action or write on the way to
    answering a read."""

    def test_THE_DECLARED_RESOLVER_IS_LANE_READ(self):
        resolvers, _ = loaded()
        assert resolvers, "the registry declares no ref type — this suite would be vacuous"
        for r in resolvers.values():
            assert lane_of(r.tool) == "read", f"{r.ref_type} resolves via {r.tool}"

    @pytest.mark.parametrize("lane", ["action", "write", "system"])
    def test_A_NON_READ_RESOLVER_IS_REFUSED_AT_REGISTRATION(self, lane):
        doc = registry_doc()
        doc["ref_types"]["EntityRef"]["resolver_tool"] = "glossary_entity_delete"
        with pytest.raises(RefContractViolation, match="lane=read"):
            load_registry(doc, lambda _t: lane)

    def test_AN_UNKNOWN_LANE_FAILS_CLOSED(self):
        """A resolver whose tool is not in the catalogue cannot be SHOWN to be a read, and
        'cannot be shown to be safe' is a refusal, not a default."""
        with pytest.raises(RefContractViolation, match="cannot determine"):
            load_registry(registry_doc(), lambda _t: None)

    def test_A_BINDING_NAMING_AN_UNDECLARED_REF_TYPE_IS_REFUSED(self):
        doc = registry_doc()
        doc["bindings"]["glossary_get_entity"] = {"entity_id": "NoSuchRef"}
        with pytest.raises(RefContractViolation, match="NoSuchRef"):
            load_registry(doc, lane_of)


class TestTwoBranchesAndNoThird:

    def _resolver(self):
        return loaded()[0]["EntityRef"]

    def test_EXACTLY_ONE_MATCH_SUBSTITUTES(self):
        r = decide(self._resolver(), "entity_id", "Lâm Uyên",
                   {"entities": [hit("Lâm Uyên")]})
        assert r.outcome == "resolved" and r.ok
        assert r.resolved == "019f0000-0000-7000-8000-000000000001"

    def test_MORE_THAN_ONE_EXACT_MATCH_REFUSES_AND_NEVER_PICKS(self):
        """🔴 The case the pilot MEASURED: `Dracula` returns four exact matches, all tied at 0.9,
        separable only by `updated_at`. A rank tiebreak here is the guess §0.14 forbids."""
        rows = [hit("Dracula", eid="a"), hit("Dracula", eid="b"),
                hit("Dracula", eid="c"), hit("Count Dracula", eid="d")]
        r = decide(self._resolver(), "entity_id", "Dracula", {"entities": rows})
        assert r.outcome == "ambiguous"
        assert r.resolved is None, "an ambiguous resolution must not substitute ANYTHING"
        assert len(r.candidates) == 4

    def test_ZERO_EXACT_MATCHES_REFUSES_WITH_THE_NEAR_MISSES(self):
        r = decide(self._resolver(), "entity_id", "Ember Codex",
                   {"entities": [hit("Ember Codicil", tier="fts")]})
        assert r.outcome == "no_match" and r.resolved is None
        assert "Ember Codicil" in refusal_message([r])

    def test_A_LOWER_QUALITY_MATCH_IS_NOT_A_MATCH(self):
        """Only the declared quality counts. An `fts` hit is a search result, not an identity."""
        r = decide(self._resolver(), "entity_id", "Dracula",
                   {"entities": [hit("Castle Dracula", tier="fts")]})
        assert r.outcome == "no_match"

    def test_THE_REFUSAL_IS_ACTIONABLE_WHERE_TODAYS_ERROR_IS_NOT(self):
        rows = [hit("Dracula", eid="a"), hit("Dracula", eid="b")]
        msg = refusal_message([decide(self._resolver(), "entity_id", "Dracula",
                                      {"entities": rows})])
        assert "Dracula" in msg and "MORE THAN ONE" in msg
        assert "cannot be guessed" in msg


class TestWhatGetsResolvedAtAll:

    def test_A_VALUE_THAT_IS_ALREADY_AN_ID_IS_LEFT_ALONE(self):
        resolvers, bindings = loaded()
        args = {"book_id": BOOK, "entity_id": "019f6531-0000-7000-8000-00000000000a"}
        assert pending_for("glossary_get_entity", args, bindings, resolvers) == []

    def test_AN_UNBOUND_TOOL_IS_NOT_TOUCHED(self):
        resolvers, bindings = loaded()
        args = {"book_id": BOOK, "entity_id": "Lâm Uyên"}
        assert pending_for("composition_find_references", args, bindings, resolvers) == []

    def test_THE_RESOLVER_CALL_IS_SCOPED_LIKE_THE_ORIGINAL(self):
        """An entity name is only unique within its book, so the scope travels with the query."""
        resolvers, bindings = loaded()
        pend = pending_for("glossary_get_entity",
                           {"book_id": BOOK, "entity_id": "Lâm Uyên"}, bindings, resolvers)
        assert pend[0].args == {"query": "Lâm Uyên", "book_id": BOOK}

    @pytest.mark.parametrize("value", ["019f6531-f4d9-7346-8f97-0b15c752fc39",
                                       "019F6531-F4D9-7346-8F97-0B15C752FC39"])
    def test_LOOKS_LIKE_AN_ID_ACCEPTS_A_UUID(self, value):
        assert looks_like_an_id(value)

    @pytest.mark.parametrize("value", ["Ember Codex", "all", "placeholder_id", "", "0",
                                       "019fcab8-9a4-7c68-90d3-0252d648325c"])
    def test_LOOKS_LIKE_AN_ID_REJECTS_EVERYTHING_ELSE(self, value):
        """Including a MANGLED uuid (a dropped nibble): resolving one would invent a match for a
        typo, and the pilot counted it as a separate defect for exactly that reason."""
        assert not looks_like_an_id(value)


class TestTheSubstitutionIsRECORDED:
    """The separation `plan_supplied.overrode` had to make: without it a resolved argument and a
    model-typed one are the same row, and the member cannot be measured at all."""

    def test_THE_RECORD_KEEPS_THE_NAME_THE_MODEL_SENT(self):
        resolvers, bindings = loaded()
        args = {"book_id": BOOK, "entity_id": "Lâm Uyên"}
        res = resolve_call("glossary_get_entity", dict(args), bindings, resolvers,
                           lambda _t, _a: {"entities": [hit("Lâm Uyên")]})
        record = apply_resolutions(args, res)
        assert args["entity_id"] == "019f0000-0000-7000-8000-000000000001"
        assert record["model_sent"] == {"entity_id": "Lâm Uyên"}, (
            "the NAME is the only evidence resolution changed the outcome; keeping just the final "
            "id makes a resolved call and a correctly-typed one the same row"
        )
        assert record["outcomes"] == {"entity_id": "resolved"}

    def test_A_REFUSED_PARAMETER_IS_NOT_SUBSTITUTED_AND_IS_RECORDED(self):
        resolvers, bindings = loaded()
        args = {"book_id": BOOK, "entity_id": "Dracula"}
        res = resolve_call("glossary_get_entity", dict(args), bindings, resolvers,
                           lambda _t, _a: {"entities": [hit("Dracula", eid="a"),
                                                        hit("Dracula", eid="b")]})
        record = apply_resolutions(args, res)
        assert args["entity_id"] == "Dracula", "a refused resolution must not alter the argument"
        assert record["refused"] == ["entity_id"]
        assert record["outcomes"] == {"entity_id": "ambiguous"}

    def test_A_RESOLVER_THAT_FAILS_IS_RECORDED_NOT_SILENTLY_IGNORED(self):
        def boom(_t, _a):
            raise RuntimeError("resolver down")

        resolvers, bindings = loaded()
        args = {"book_id": BOOK, "entity_id": "Lâm Uyên"}
        res = resolve_call("glossary_get_entity", dict(args), bindings, resolvers, boom)
        record = apply_resolutions(args, res)
        assert record["outcomes"] == {"entity_id": "resolver_failed"}
        assert args["entity_id"] == "Lâm Uyên", "a failed resolver is not a licence to guess"


class TestTheMechanismIsREACHABLEFromProduction:
    """🔴 **THE SHAPE THIS RUN KEEPS FINDING.** In two days: `sweep_expired_runs` with no caller,
    `agentruntime_arm` with no compose entry, `resolve_arguments` with zero production callers,
    `check_transition` with zero production callers. A resolver nothing dispatches would be the
    fifth. These guard the two ways it could be present and inert."""

    def test_THE_DISPATCH_CHOKEPOINT_ACTUALLY_CALLS_THE_RESOLVER(self):
        """A source-level check on purpose: importing `stream_service` needs the full service
        config, and the claim here is about a CALL SITE existing in the shipped path, which is
        exactly what a grep can settle and a mock cannot."""
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        assert "_ref_pending(" in src, "nothing in the dispatch path asks what needs resolving"
        assert "_ref_decide(" in src, "nothing in the dispatch path decides a resolution"
        assert "unresolved_reference" in src, "the refusal branch never reaches the model"
        assert 'tool_chunk["resolution"]' in src, (
            "a resolution that is not recorded on the call cannot be measured, which is how the "
            "round-2 V-METRIC table became half theatre"
        )

    def test_THE_REGISTRY_FILE_IS_WHERE_THE_LOADER_LOOKS(self):
        """`agentruntime_arm` was a flag with no deployment path. This is the same question asked
        of the registry: the loader resolves it beside the manifest, so it must BE there."""
        from app.agentruntime.manifest import manifest_path
        from app.agentruntime.refresolve import REF_REGISTRY_FILENAME
        mpath = manifest_path()
        assert mpath is not None, "no manifest anchor — the loader would find nothing"
        assert (mpath.parent / REF_REGISTRY_FILENAME).exists(), (
            f"the loader looks for {REF_REGISTRY_FILENAME} beside the manifest and it is not there"
        )
        assert (mpath.parent / REF_REGISTRY_FILENAME) == REGISTRY


class TestTheBindingsCoverWhatActuallyFAILED:

    #: Every (tool, param) that produced a real `must be a UUID` failure with a NAME in it,
    #: from `scripts/cp5-resolution-pilot.py` over `loreweave_chat`.
    FAILED = [("glossary_list_chapter_links", "entity_id"),
              ("glossary_get_entity", "entity_id"),
              ("glossary_list_entity_revisions", "entity_id"),
              ("glossary_entity_set_attributes", "entity_id"),
              ("glossary_propose_merge", "winner_id")]

    def test_EVERY_TOOL_PARAM_THAT_ACTUALLY_FAILED_IS_BOUND(self):
        _, bindings = loaded()
        missing = [tp for tp in self.FAILED if tp not in bindings]
        assert missing == [], (
            f"{missing} produced real failures and no resolver is bound to them — the member would "
            f"not serve the population it was built for"
        )

    def test_EVERY_BINDING_NAMES_A_REAL_PARAMETER_OF_A_REAL_TOOL(self):
        _, bindings = loaded()
        props = {}
        for t in catalogue():
            fn = t.get("function", t)
            props[fn.get("name")] = set(((fn.get("inputSchema") or {}).get("properties") or {}))
        for tool, param in bindings:
            assert tool in props, f"{tool} is bound but not in the catalogue"
            assert param in props[tool], f"{tool}.{param} is bound but the tool has no such param"

    def test_EVERY_BOUND_TOOL_CARRIES_THE_RESOLVERS_SCOPE(self):
        """A book-scoped resolver bound to a tool with no `book_id` could only ever resolve
        against the wrong book, or not at all."""
        resolvers, bindings = loaded()
        props = {}
        for t in catalogue():
            fn = t.get("function", t)
            props[fn.get("name")] = set(((fn.get("inputSchema") or {}).get("properties") or {}))
        for (tool, param), ref_type in bindings.items():
            for scope in resolvers[ref_type].scope_params:
                assert scope in props[tool], f"{tool}.{param} lacks scope {scope}"

    def test_THE_UNBOUND_ENTITY_REF_PARAMS_ARE_STATED(self):
        """🔴 Coverage is not claimed where it does not exist. Catalogue params named `entity_id`
        outside glossary are scoped differently (composition/kg/world/lore), so a book-scoped
        resolver would be WRONG there — they are deliberately unbound, and this keeps that visible
        instead of letting the member look complete."""
        _, bindings = loaded()
        unbound = []
        for t in catalogue():
            fn = t.get("function", t)
            name = fn.get("name", "")
            for p in ((fn.get("inputSchema") or {}).get("properties") or {}):
                if p in ("entity_id", "winner_id") and (name, p) not in bindings:
                    unbound.append(f"{name}.{p}")
        assert sorted(unbound) == [
            "composition_canon_rule_create.entity_id",
            "composition_canon_rule_edit.entity_id",
            "composition_find_references.entity_id",
            "kg_entity_edge_timeline.entity_id",
            "lore_entity.entity_id",
            "world_map_add_marker.entity_id",
            "world_map_add_region.entity_id",
            "world_map_update_marker.entity_id",
            "world_map_update_region.entity_id",
        ], (
            "the unbound set changed. That is not automatically wrong — but it is a decision about "
            "which populations this member serves, and it must be made deliberately"
        )
