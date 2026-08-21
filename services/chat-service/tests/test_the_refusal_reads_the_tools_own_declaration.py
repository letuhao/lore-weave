"""The refusal told the model nothing was declared while the declaration sat in the tool def.

`_missing_args_message` decided "this tool does not declare which side supplies them" from the
CONTRACT REGISTRY — and only 12 of the 315 federated tools carry a contract, so that arm fires for
almost everything. But a tool's PROPERTY DESCRIPTION is a declaration too, and on this platform it
is usually the only one: 219 `*_id` properties state UUID in prose and zero emit `format: uuid`.

MEASURED 2026-08-14. composition_generate's `model_ref` was given a description naming its
supplier — "The model's id (UUID). NOT a name, an alias, or 'default' — list the caller's models
with settings_list_models and pass the `model_ref` from there." — and the refusal still read:

    'composition_generate' is missing required argument(s): ['model_ref'], and this tool does
    not declare which side supplies them — so do NOT guess a value.

The runtime was holding the answer and telling the model it had none. On 4 of 5 runs the model
then abandoned the grounded tool entirely and proposed book_chapter_save_draft carrying prose it
had written itself. On the 1 run that did call settings_list_models and come back with a real
model id, it got there in spite of this sentence, not because of it.

🔴 THE ARM ORDER MATTERS AND IS PINNED BELOW. The `context|plan` arm still wins first — those
arguments are genuinely not the model's to invent, and that sentence is the stronger one. The
description arm only replaces the "does not declare" fallback, and the fallback itself is kept
intact for arguments that really do declare nothing.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.stream_service import _missing_args_message  # noqa: E402

#: composition_generate's real declaration after this cycle.
GEN_PROPS = {
    "model_ref": {"type": "string", "description": (
        "The model's id (UUID). NOT a name, an alias, or 'default' — list the caller's models "
        "with settings_list_models and pass the `model_ref` from there.")},
}


class TestItQuotesWhatTheToolActuallyDeclares:
    """THE FALSIFIER — the exact call that produced the contradiction."""

    def test_it_no_longer_claims_nothing_is_declared(self):
        msg = _missing_args_message("composition_generate", ["model_ref"], {}, GEN_PROPS)
        assert "does not declare which side supplies" not in msg

    def test_it_names_the_supplier_the_tool_named(self):
        msg = _missing_args_message("composition_generate", ["model_ref"], {}, GEN_PROPS)
        assert "settings_list_models" in msg, (
            "the supplier is in the tool's own description — the refusal must pass it on")

    def test_it_still_forbids_the_placeholder(self):
        msg = _missing_args_message("composition_generate", ["model_ref"], {}, GEN_PROPS)
        assert "default" in msg and "guess" in msg.lower()

    def test_the_argument_is_still_named(self):
        msg = _missing_args_message("composition_generate", ["model_ref"], {}, GEN_PROPS)
        assert "model_ref" in msg


class TestTheGenuinelyUndeclaredCaseIsUnchanged:
    """The fallback is kept, not replaced — an argument that declares nothing must still say so
    rather than quote an empty string at the model."""

    def test_no_props_at_all_keeps_the_old_sentence(self):
        msg = _missing_args_message("some_tool", ["thing_id"], {}, None)
        assert "does not declare which side supplies" in msg

    def test_an_empty_description_is_not_treated_as_a_declaration(self):
        props = {"thing_id": {"type": "string", "description": "   "}}
        msg = _missing_args_message("some_tool", ["thing_id"], {}, props)
        assert "does not declare which side supplies" in msg

    def test_a_missing_description_key_is_not_treated_as_a_declaration(self):
        props = {"thing_id": {"type": "string"}}
        msg = _missing_args_message("some_tool", ["thing_id"], {}, props)
        assert "does not declare which side supplies" in msg


class TestTheContextPlanArmStillWinsFirst:
    """🔴 Arm order. A context/plan argument is NOT the model's to invent whatever its description
    says, so that sentence must not be softened into 'here is how to get it'."""

    def test_a_plan_supplied_arg_keeps_its_own_refusal(self):
        block = {"argument_supplier": {"run_id": "plan — the rail owns it"}}
        props = {"run_id": {"type": "string", "description": "the run id (UUID)"}}
        msg = _missing_args_message("plan_compile", ["run_id"], block, props)
        assert "NOT yours to invent" in msg


class TestTheCallSitePassesTheProperties:
    """CALL-SITE GUARD. The new arm is inert if the properties never arrive — and the default is
    None, which falls straight back to the old sentence and looks exactly like the defect."""

    def test_the_properties_are_threaded_from_the_catalog(self):
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        # Anchored on the BINDING, not on a byte window after the call: the properties are
        # resolved into `_ma_props` first (one lookup, so an anchored falsifier that counts
        # occurrences of the catalog expression stays valid). This test caught that refactor,
        # which is the guard working rather than a nuisance.
        i = src.index("_ma_props = (")
        j = src.index("_ma_msg = _missing_args_message(", i)
        binding = src[i:j]
        assert "cat_index.get(" in binding, "the properties no longer come from the catalog"
        assert '"properties"' in binding
        call = src[j:j + 200]
        assert "_ma_props)" in call, "the resolved properties are not passed to the helper"
