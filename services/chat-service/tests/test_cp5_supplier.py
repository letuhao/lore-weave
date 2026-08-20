"""CP-5.4 — every input declares WHO SUPPLIES IT, and the refusal says so.

🔴 **ONE SENTENCE WAS COVERING TWO OPPOSITE SITUATIONS.** Measured over 266 missing-argument
failures across 87 sessions: the single largest case is **`book_read` missing `book_id` — 78 calls
over 46 sessions** — and `book_id` is a **context** value. The runtime fills it from the ambient
book and has none outside a book studio. The model was told *"missing required argument book_id"*,
which reads as *you forgot something* when the truth is *I owe you this and do not have it* — and
the model cannot act on the difference.

The rest (`body`, `items`, `base_version`) are genuinely `model`-supplied content, and for those
that message is already right. Telling them apart is the whole row, and it is the same defect as
`ok:false` covering both a failure and a suspension (5.5), one layer up.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from app.agentruntime.toolcontract import SUPPLIERS, declared_supplier, resolve_contract

REGISTRY = (pathlib.Path(__file__).resolve().parents[3]
            / "contracts" / "agent-runtime-tool-contracts.json")


def registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def contract_for(tool: str) -> dict:
    block, _ = resolve_contract({"name": tool}, registry())
    return block


class TestTheSupplierIsReadableFromTheContract:

    def test_THE_DOMINANT_REAL_FAILURE_IS_A_CONTEXT_VALUE(self):
        """`book_read.book_id` — 78 calls / 46 sessions, the largest single missing-argument
        class in the corpus. If this ever reads `model`, the row's whole premise is gone."""
        assert declared_supplier(contract_for("book_read"), "book_id") == "context"

    def test_A_CONTENT_ARGUMENT_IS_THE_MODELS(self):
        assert declared_supplier(contract_for("book_list"), "kind") == "model"

    def test_A_PLAN_BOUND_ARGUMENT_READS_AS_OWED_BY_THE_RUNTIME(self):
        assert declared_supplier(contract_for("book_read"), "chapter_id") == "plan"

    def test_AN_UNDECLARED_PARAMETER_IS_NONE_NOT_A_GUESS(self):
        assert declared_supplier(contract_for("book_read"), "no_such_param") is None
        assert declared_supplier({}, "book_id") is None

    def test_EVERY_DECLARED_SUPPLIER_NAMES_A_KNOWN_SIDE(self):
        """A supplier outside the vocabulary would silently read as `model`'s opposite or as
        nothing at all, and the message would go back to being generic without anyone noticing."""
        for tool, block in registry()["contracts"].items():
            for param in (block.get("argument_supplier") or {}):
                got = declared_supplier(block, param)
                assert got in SUPPLIERS, f"{tool}.{param} declares {got!r}"

    def test_THE_RUNTIME_IS_PREFERRED_OVER_THE_MODEL_WHEN_BOTH_APPEAR(self):
        """`"context | model"` means the runtime owes it and the model may also pass it — the
        runtime wins, or the work goes back to the model exactly where it need not.

        🔴 The first version of this asserted `"context | plan"` → `context`, which is true under
        ANY ordering of the three suppliers, so the falsifier that reordered them left the guard
        green: *"the guard requires nothing"*. The case has to be one where the order DECIDES.
        """
        assert declared_supplier(
            {"argument_supplier": {"x": "context | model — either"}}, "x") == "context"
        assert declared_supplier(
            {"argument_supplier": {"x": "plan | model — either"}}, "x") == "plan"
        assert declared_supplier(
            {"argument_supplier": {"x": "model — only the caller knows"}}, "x") == "model"

    def test_PROSE_AFTER_THE_DASH_IS_NOT_PARSED_FOR_SUPPLIERS(self):
        """The declaration is `supplier — explanation`, and the explanation is for a human.

        🔴 The first version used `"context — … the model …"`, where reading the prose ALSO yields
        `context` (it sorts first), so parsing the whole string changed nothing and the guard could
        not fail. The discriminating case is a MODEL-supplied input whose prose mentions context:
        parse the prose and the answer flips to `context`, handing the runtime an argument only the
        caller can write.
        """
        got = declared_supplier(
            {"argument_supplier": {"x": "model — the caller writes this from context they hold"}},
            "x")
        assert got == "model", "the explanation is for a human and must not decide the supplier"


class TestTheRefusalTellsTheModelWhoOwesIt:

    def test_THE_MESSAGE_DISTINGUISHES_OWED_FROM_MISSING(self):
        """The branch must exist and must key off the DECLARED supplier, not off a list of tool
        names kept in the stream module.

        Asserted BEHAVIOURALLY now rather than by substring. The arms moved into
        `_missing_args_message` when the undeclared case was split out, and a source-level grep for
        the old inline expression would have gone red on a pure refactor while staying green on a
        message that consulted nothing — the wrong way round for a guard.
        """
        from app.services.stream_service import _missing_args_message
        block = {"argument_supplier": {"book_id": "context — the ambient book"}}
        assert "NOT yours to invent" in _missing_args_message("book_read", ["book_id"], block)
        # …and a supplier the contract calls the model's own must NOT get that sentence.
        model_block = {"argument_supplier": {"items": "model — the caller writes these"}}
        assert "NOT yours to invent" not in _missing_args_message(
            "book_write", ["items"], model_block)

    def test_A_MODEL_SUPPLIED_ARGUMENT_KEEPS_THE_ORIGINAL_MESSAGE(self):
        """`body` and `items` are the model's to write. Rewriting their message as *"the runtime
        owes you this"* would be the same error pointed the other way."""
        block = contract_for("book_list")
        owed = [p for p in ("kind", "limit")
                if declared_supplier(block, p) in ("context", "plan")]
        assert owed == [], f"{owed} would wrongly be reported as runtime-owed"


class TestARefusalArmsTheToolsItNames:
    """🔴 MEASURED LIVE 2026-08-12, journey `kg-build` (session 019ff498-7603…).

    kg_build refused with "call kg_project_set_embedding_model first (pick one of your embedding
    models with settings_list_models)". Both tools are federated, and NEITHER was in that turn's
    advertised surface. The model understood the requirement, wrote "I'll get to work on setting
    that up now" three times, never called either tool, retried kg_build unchanged, and asked the
    author whether to keep trying. An instruction naming an unreachable tool cannot be followed.
    """

    def test_the_tools_a_refusal_names_are_selected_for_arming(self):
        from app.services.stream_service import _tools_named_in_refusal
        err = ("this project has no embedding model configured — call "
               "kg_project_set_embedding_model first (pick one of your embedding models with "
               "settings_list_models), then retry this build")
        catalog = {"kg_project_set_embedding_model": {}, "settings_list_models": {}, "kg_build": {}}
        got = _tools_named_in_refusal(err, catalog, {"kg_build"})
        assert got == ["kg_project_set_embedding_model", "settings_list_models"]

    def test_a_tool_ALREADY_on_the_surface_is_not_rearmed(self):
        from app.services.stream_service import _tools_named_in_refusal
        catalog = {"settings_list_models": {}}
        assert _tools_named_in_refusal("use settings_list_models", catalog,
                                       {"settings_list_models"}) == []

    def test_a_SUBSTRING_of_a_tool_name_does_not_arm_it(self):
        """`kg_build` sits inside `kg_build_wiki`. A substring test would arm the wrong tool off its
        own refusal — the mrows.Err()/rows.Err() shape that kept a guard green while the check it
        named was deleted."""
        from app.services.stream_service import _tools_named_in_refusal
        catalog = {"kg_build": {}}
        assert _tools_named_in_refusal("kg_build_wiki failed", catalog, set()) == [], (
            "a tool name matched inside a LONGER tool name"
        )

    def test_the_CALL_SITE_arms_what_the_refusal_named(self):
        """Guard the call site: a selector nothing calls changes no live turn."""
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        # The ASSIGNMENT, not the bare name: `def _tools_named_in_refusal(` also contains
        # "_tools_named_in_refusal(", so grepping for that alone stays green with the call site
        # deleted — the guard would have been guarding its own definition.
        assert "_recovery = _tools_named_in_refusal(" in src
        assert "no tool_load needed" in src
        assert "merge_activated_tools" in src


class TestAnUndeclaredArgumentIsNotCalledContent:
    """The third case CP-5.4 folded into the model-supplied arm.

    🔴 MEASURED LIVE 2026-08-12, journey `draw-a-map`: `world_map_create` was called without
    `world_id` and refused with *"These carry the actual CONTENT (not ids the system already
    fills) … Do not call it with only ids or empty arguments."* The one missing argument IS an id.
    The model was told the thing it lacked was not the thing it lacked, stopped calling tools, and
    reported *"I have initialized the map"* over a map that never existed. Only 12 of the 315
    federated tools declare a contract, so undeclared is the COMMON path.
    """

    def test_an_UNDECLARED_id_is_never_described_as_not_an_id(self):
        from app.services.stream_service import _missing_args_message
        msg = _missing_args_message("world_map_create", ["world_id"], {})
        assert "not ids the system already fills" not in msg, (
            "the refusal asserts the missing argument is not an id, and it is one"
        )
        assert "Do not call it with only ids" not in msg
        assert "world_id" in msg

    def test_an_UNDECLARED_id_is_given_the_move_that_obtains_it(self):
        """C-12: the rejection names what WOULD be legal. For an id that is 'go list them'."""
        from app.services.stream_service import _missing_args_message
        msg = _missing_args_message("world_map_create", ["world_id"], {})
        assert "LISTS or SEARCHES" in msg
        assert "do NOT guess" in msg or "Do NOT guess" in msg

    def test_a_DECLARED_context_argument_still_says_not_yours_to_invent(self):
        """The CP-5.4 arm must be untouched by the new one."""
        from app.services.stream_service import _missing_args_message
        block = {"argument_supplier": {"book_id": "context — the ambient book"}}
        msg = _missing_args_message("book_read", ["book_id"], block)
        assert "NOT yours to invent" in msg

    def test_a_DECLARED_model_argument_still_gets_the_CONTENT_message(self):
        """And so must the arm it was folded into — an undeclared arg borrowed this sentence, a
        genuinely model-supplied one is entitled to it."""
        from app.services.stream_service import _missing_args_message
        block = {"argument_supplier": {"entities": "model — the caller writes these"}}
        msg = _missing_args_message("glossary_propose_entities", ["entities"], block)
        assert "carry the actual CONTENT" in msg

    def test_the_CALL_SITE_uses_the_helper_not_its_own_sentence(self):
        """Guard the call site, not the helper: a message builder nothing calls is decoration, and
        the inline copy is exactly what shipped the defect."""
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        assert "_ma_msg = _missing_args_message(" in src, (
            "the S02 refusal path does not call _missing_args_message, so the undeclared arm "
            "cannot reach a live call"
        )
        assert src.count("These carry the actual CONTENT") == 1, (
            "the model-supplied sentence exists in more than one place; the inline copy is how "
            "the undeclared case silently inherited it"
        )


class TestASingleElementListForAScalarArgIsRepaired:
    """🔴 MEASURED LIVE 2026-08-12, journey `translation-pass` (book 019f9a02-f3a3…).

    translation_start_job was called with target_language=["vi"] and refused: "Input should be 'en',
    'vi', … (you sent ['vi'])". The refusal names the legal set and what was sent, and the turn
    still ended there with the journey unfinished. The value was already correct; only its container
    was wrong.
    """

    @staticmethod
    def _def(name, spec):
        return {"function": {"name": "t", "parameters": {"properties": {name: spec}}}}

    def test_a_scalar_enum_gets_its_value_unwrapped(self):
        from app.services.stream_service import _unwrap_single_element_scalar_args
        args = {"target_language": ["vi"]}
        got = _unwrap_single_element_scalar_args(
            args, self._def("target_language", {"type": "string", "enum": ["en", "vi"]}))
        assert got == ["target_language"]
        assert args["target_language"] == "vi"

    def test_an_ARRAY_typed_arg_is_never_unwrapped(self):
        """The control that matters most: unwrapping a real list silently corrupts the call.

        🔴 The first version declared `{"type": "array", "items": {...}}`, which the `items` check
        already skips — so it stayed green with the array-type test deleted and the harness reported
        "the guard requires nothing". The discriminating spec is an array with NO `items`, where
        only `"array" in types` stands between a declared list and a flattened one.
        """
        from app.services.stream_service import _unwrap_single_element_scalar_args
        args = {"entity_ids": ["abc"]}
        got = _unwrap_single_element_scalar_args(
            args, self._def("entity_ids", {"type": "array"}))
        assert got == []
        assert args["entity_ids"] == ["abc"], "a declared array argument was flattened to a scalar"

    def test_a_UNION_type_containing_array_is_not_unwrapped(self):
        """JSON Schema `type` can be a LIST, and reading only part of it re-opens the hole.

        🔴 The first version used `["null", "array"]`, where dropping the array member leaves
        `null` — still not scalar, so it declined anyway and the guard required nothing. The
        discriminating union is `["string", "array"]`: honour only the scalar member and the value
        IS unwrapped; the array member has to disqualify it.
        """
        from app.services.stream_service import _unwrap_single_element_scalar_args
        args = {"tags": ["x"]}
        got = _unwrap_single_element_scalar_args(
            args, self._def("tags", {"type": ["string", "array"]}))
        assert got == []
        assert args["tags"] == ["x"]

    def test_a_list_of_MORE_THAN_ONE_is_left_alone(self):
        """['vi','en'] is a real disagreement about cardinality, not a container slip — it must
        still reach the refusal rather than be silently truncated to its first element."""
        from app.services.stream_service import _unwrap_single_element_scalar_args
        args = {"target_language": ["vi", "en"]}
        assert _unwrap_single_element_scalar_args(
            args, self._def("target_language", {"type": "string"})) == []
        assert args["target_language"] == ["vi", "en"]

    def test_an_UNDECLARED_param_is_left_alone(self):
        from app.services.stream_service import _unwrap_single_element_scalar_args
        args = {"mystery": ["v"]}
        assert _unwrap_single_element_scalar_args(args, self._def("other", {"type": "string"})) == []
        assert args["mystery"] == ["v"]

    def test_the_CALL_SITE_repairs_before_the_missing_arg_check(self):
        """Guard the call site: repairing after validation would change nothing a caller sees."""
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        assert "_unwrapped = _unwrap_single_element_scalar_args(" in src
        i_fix = src.index("_unwrapped = _unwrap_single_element_scalar_args(")
        i_chk = src.index("_missing_args = _missing_required_names(")
        assert i_fix < i_chk, "the repair runs after the missing-argument check"


    def test_the_REAL_optional_enum_shape_from_the_catalogue_is_repaired(self):
        """The shape that actually motivated this, copied from the live catalogue rather than
        invented: translation_start_job.target_language declares
        `anyOf: [{enum:[...], type: string}, {type: null}]` — pydantic's rendering of `X | None`.

        🔴 The first version of the repair declined every `anyOf`, so it could not fire on the one
        call it was written for. A rule that never reaches the real corpus is decoration; this guard
        is what stops it regressing to that.
        """
        from app.services.stream_service import _unwrap_single_element_scalar_args
        spec = {"anyOf": [{"enum": ["en", "vi", "ja"], "type": "string"}, {"type": "null"}],
                "default": None, "title": "Target Language"}
        args = {"target_language": ["vi"]}
        got = _unwrap_single_element_scalar_args(args, self._def("target_language", spec))
        assert got == ["target_language"], "the real optional-enum shape was not repaired"
        assert args["target_language"] == "vi"

    def test_a_UNION_with_an_ARRAY_branch_is_still_refused(self):
        """The safety property must survive the anyOf widening: a union that CAN be a list is never
        flattened, or the widening would have traded a refused call for a corrupted one."""
        from app.services.stream_service import _unwrap_single_element_scalar_args
        spec = {"anyOf": [{"type": "string"}, {"type": "array"}]}
        args = {"scope": ["x"]}
        assert _unwrap_single_element_scalar_args(args, self._def("scope", spec)) == []
        assert args["scope"] == ["x"]


class TestAStalledRailWriteIsCaughtWhenNoToolWasNamed:
    """🔴 MEASURED LIVE 2026-08-12, book 019f9a02-f3a3…. Asked "Please translate this book into
    Vietnamese for me now", the model answered "I've started the translation for Chapter 1 into
    Vietnamese. I'll monitor the progress…" with ZERO tool calls, outcome='completed', and no job
    row. It named no tool, so `_narrated_uncalled_writes` (which intersects prose with real tool
    NAMES) saw nothing and no D-NARRATED-WRITE line was logged. The plainer phrasing — the one a
    user actually gets — was structurally invisible.
    """

    class _Step:
        def __init__(self, tool): self.tool = tool

    class _Prog:
        def __init__(self, tool): self.next_step = TestAStalledRailWriteIsCaughtWhenNoToolWasNamed._Step(tool)

    # The catalogue shape tool_tier actually reads: `_meta` lives INSIDE `function`.
    WRITE = {"translation_start_job": {"function": {"_meta": {"tier": "A"}}}}

    def test_a_turn_that_called_NOTHING_with_a_rail_write_outstanding_is_caught(self):
        from app.services.stream_service import _rail_write_step_stalled
        got = _rail_write_step_stalled(
            [self._Prog("translation_start_job")], catalog_index=self.WRITE, attempted=set())
        assert got == "translation_start_job"

    def test_a_turn_that_ATTEMPTED_a_tool_is_left_alone(self):
        """A model that tried and got a real error already has honest feedback — nudging there is
        noise, and the sister guard excludes it for the same reason."""
        from app.services.stream_service import _rail_write_step_stalled
        assert _rail_write_step_stalled(
            [self._Prog("translation_start_job")], catalog_index=self.WRITE,
            attempted={"translation_coverage"}) is None

    def test_a_rail_whose_next_step_is_a_READ_is_left_alone(self):
        """Nothing was claimed to have changed, so there is nothing for the author to not find."""
        from app.services.stream_service import _rail_write_step_stalled
        assert _rail_write_step_stalled(
            [self._Prog("translation_coverage")],
            catalog_index={"translation_coverage": {"function": {"_meta": {"tier": "R"}}}},
            attempted=set()) is None

    def test_no_rail_means_no_nudge(self):
        """An ordinary conversation with no journey outstanding must never be nudged."""
        from app.services.stream_service import _rail_write_step_stalled
        assert _rail_write_step_stalled(None, catalog_index=self.WRITE, attempted=set()) is None
        assert _rail_write_step_stalled([], catalog_index=self.WRITE, attempted=set()) is None

    def test_a_rail_with_NO_next_step_is_left_alone(self):
        from app.services.stream_service import _rail_write_step_stalled
        class _Done: next_step = None
        assert _rail_write_step_stalled([_Done()], catalog_index=self.WRITE, attempted=set()) is None

    def test_the_DIRECTIVE_for_this_arm_claims_nothing_it_did_not_measure(self):
        """It never read the prose, so it must not say "you just described using X" — asserting an
        unmeasured claim is the same false-report defect pointed the other way."""
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        assert "This turn called no tool at all" in src
        assert "_stalled_tool = _rail_write_step_stalled(" in src
        # 🔴 CAUGHT ON A LIVE RUN by reading this guard's own log output: the two arms shared one
        # WARNING line, so the stalled-rail arm logged "named in prose" about prose it never read.
        # The directive was careful and the log was not.
        assert "the turn called NO tool while a rail's next write step is " in src


class TestAFabricatedRuntimeOwnedIdIsTreatedAsMissing:
    """🔴 MEASURED LIVE 2026-08-12, journey `autonomous-drafting`, book 019ff497.

    The model called plan_compile with run_id="run_12345_placeholder" and the tool answered "run_id
    must be a UUID" -- correct about the TYPE, silent about the thing that matters. run_id is a PLAN
    value emitted by plan_propose_spec; it is not the model's to invent, so arguing about its format
    invites a better-formatted invention. CP-5.4 learned this for MISSING arguments; a fabricated one
    is the same state with a placeholder written over it.
    """

    PLAN = {"argument_supplier": {"run_id": "plan — emitted by a prior plan_propose_spec step"}}

    def test_the_LIVE_placeholder_is_caught(self):
        from app.services.stream_service import _invented_supplier_ids
        assert _invented_supplier_ids({"run_id": "run_12345_placeholder"}, self.PLAN) == ["run_id"]

    def test_a_VALID_uuid_is_accepted_even_if_it_is_the_wrong_row(self):
        """Whether it is the RIGHT row is the tool's question, not ours — refusing a well-formed id
        here would break every legitimate plan-bound call."""
        from app.services.stream_service import _invented_supplier_ids
        assert _invented_supplier_ids(
            {"run_id": "019ff486-8eaf-7c6d-97f2-e0567037bffd"}, self.PLAN) == []

    def test_a_MODEL_supplied_id_is_none_of_our_business(self):
        from app.services.stream_service import _invented_supplier_ids
        block = {"argument_supplier": {"arc_id": "model — the caller's choice"}}
        assert _invented_supplier_ids({"arc_id": "arc_1"}, block) == []

    def test_an_UNDECLARED_id_is_left_alone(self):
        """D-FJ-2's rule: with no declaration the runtime knows nothing and must not guess."""
        from app.services.stream_service import _invented_supplier_ids
        assert _invented_supplier_ids({"run_id": "whatever"}, {}) == []

    def test_a_NON_id_argument_is_never_touched(self):
        from app.services.stream_service import _invented_supplier_ids
        block = {"argument_supplier": {"mode": "plan — chosen by the rail"}}
        assert _invented_supplier_ids({"mode": "rules"}, block) == []

    def test_the_refusal_is_the_OWED_sentence_not_a_type_complaint(self):
        """The whole point: the model must be told it does not own this value, not that it spelled
        it wrong."""
        from app.services.stream_service import _missing_args_message
        msg = _missing_args_message("plan_compile", ["run_id"], self.PLAN)
        assert "NOT yours to invent" in msg
        assert "must be a UUID" not in msg

    def test_the_CALL_SITE_drops_the_fabricated_value_before_dispatch(self):
        """Guard the call site: leaving the placeholder in args would send it to the tool anyway and
        the honest message would be decoration."""
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        assert "_invented_ids = _invented_supplier_ids(" in src
        assert "args_obj.pop(_nm, None)" in src

    def test_the_CONTRACT_declares_the_ids_the_live_run_fabricated(self):
        """A checker with nothing to check is decoration -- plan_compile.run_id must be DECLARED, or
        the undeclared arm stays silent and this never fires."""
        assert declared_supplier(contract_for("plan_compile"), "run_id") == "plan"
        assert declared_supplier(contract_for("plan_bootstrap_apply"), "proposal_id") == "plan"

    def test_a_non_uuid_CONTEXT_id_is_left_alone(self):
        """🔴 THE CONTROL THE SUITE HAD TO TEACH ME. The first draft also fired on `context` ids and
        deleted `book_id="b1"` — a value the RUNTIME injects upstream and which is not guaranteed to
        be a UUID — breaking the dispatch entirely (5 tests red). A context id is not the one the
        model invents; a plan id is."""
        from app.services.stream_service import _invented_supplier_ids
        block = {"argument_supplier": {"book_id": "context — the ambient book"}}
        args = {"book_id": "b1"}
        assert _invented_supplier_ids(args, block) == []
        assert args["book_id"] == "b1"


class TestTheOwedRefusalNamesTheToolThatEmitsTheId:
    """🔴 MEASURED LIVE 2026-08-12, right after D-FJ-11 made the refusal honest.

    The model was correctly told run_id is "NOT yours to invent ... Establish that context first
    (e.g. list or open the book you mean, then call this with the id it returns)" -- and it retried
    plan_compile TWICE, because that sentence names no tool. The emitter was already written down in
    the contract's own identifier_resolution prose and the message threw it away.
    """

    def test_the_refusal_names_the_emitting_tool(self):
        from app.services.stream_service import _missing_args_message
        block = {"argument_supplier": {"run_id": "plan — emitted by a prior step"}}
        msg = _missing_args_message("plan_compile", ["run_id"], block)
        assert "plan_propose_spec" in msg
        assert "list or open the book you mean" not in msg

    def test_naming_it_also_ARMS_it(self):
        """The compose with D-FJ-4: the arming arm keys off catalogue names in the refusal text, so a
        refusal that names the emitter makes it reachable in the same move."""
        from app.services.stream_service import _missing_args_message, _tools_named_in_refusal
        block = {"argument_supplier": {"run_id": "plan — emitted by a prior step"}}
        msg = _missing_args_message("plan_compile", ["run_id"], block)
        assert _tools_named_in_refusal(msg, {"plan_propose_spec": {}}, set()) == ["plan_propose_spec"]

    def test_with_NO_declared_emitter_the_generic_sentence_survives(self):
        """The control. Most contracts declare no emitter, and inventing one would be a guess -- the
        old sentence must still be there for them."""
        from app.services.stream_service import _missing_args_message
        block = {"argument_supplier": {"book_id": "context — the ambient book"}}
        msg = _missing_args_message("book_read", ["book_id"], block)
        assert "NOT yours to invent" in msg
        assert "Establish that context first" in msg

    def test_the_CONTRACT_declares_the_emitter_structurally(self):
        """Declared as DATA, not parsed out of identifier_resolution's prose -- behaviour must not be
        decided by an explanation written for a human."""
        from app.agentruntime.toolcontract import declared_emitter
        reg = registry()
        assert declared_emitter(reg, "plan_compile", "run_id") == "plan_propose_spec"
        assert declared_emitter(
            reg, "plan_bootstrap_apply", "proposal_id") == "plan_bootstrap_propose"
        assert declared_emitter(reg, "plan_compile", "book_id") is None
