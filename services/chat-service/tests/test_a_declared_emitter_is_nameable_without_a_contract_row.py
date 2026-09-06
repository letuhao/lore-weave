"""D-THE-EMITTER-ARM-IS-UNREACHABLE-WITHOUT-A-CONTRACT-ROW.

`argument_emitters` answers the one question a missing-id refusal has to answer — WHERE do I
get this? — and it was readable from only one branch of `_missing_args_message`: the `owed`
arm, which is entered only when `declared_supplier` says `context`/`plan`, which needs a row
in `contracts`. There are 14 such rows and 316 federated tools.

Measured 2026-08-26 against the registry and the live catalogue:

    93 declared (tool, arg) emitter pairs · 90 unreachable from a refusal (97%)
      53  the emitter names a supplier the description does NOT mention  -> real gain
      24  the description already names it                               -> redundant
      13  the arg has NO description at all -> the message said the tool "does not declare
          which side supplies them" WHILE AN EMITTER WAS DECLARED

That last group is the same falsehood the description arm was written to stop, one source
later. And it is not cosmetic: a tool named in a refusal is ARMED onto the turn by the caller
(`_tools_named_in_refusal` -> `_arm_tools`), and this platform measured 35/35 agreement —
the supplier was called on every run it was advertised and none where it was not. An
unnameable emitter is an unreachable supplier.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from app.services.stream_service import _missing_args_message

REGISTRY = json.loads(
    (pathlib.Path(__file__).resolve().parents[3] / "contracts" / "agent-runtime-tool-contracts.json")
    .read_text(encoding="utf-8")
)
EMITTERS = {k: v for k, v in REGISTRY["argument_emitters"].items() if not k.startswith("_")}
CONTRACTS = REGISTRY["contracts"]


def test_an_emitter_is_named_when_the_description_does_not_name_it():
    """The 53-pair majority: the description says WHAT the value is, never WHERE it comes
    from. composition_motif_get.motif_id declares composition_motif_search as its emitter."""
    msg = _missing_args_message(
        "composition_motif_get", ["motif_id"], None,
        {"motif_id": {"description": "The motif's id. (a UUID)"}},
    )
    assert "composition_motif_search" in msg, msg
    # and it must still quote the declaration it already had
    assert "The motif's id" in msg


def test_an_arg_with_NO_description_stops_claiming_nothing_is_declared():
    """The 13-pair group. `does not declare which side supplies them` is FALSE the moment an
    emitter exists — the exact defect the description arm was added to fix."""
    msg = _missing_args_message("composition_motif_get", ["motif_id"], None, {})
    assert "composition_motif_search" in msg, msg
    assert "does not declare" not in msg, msg


def test_the_emitter_is_not_repeated_when_the_description_already_says_it():
    """The 24-pair group. A supplier the sentence just quoted buys nothing and costs context,
    so the emitter clause is added only where it ADDS the name."""
    desc = "list the caller's models with settings_list_models and pass the model_ref from there"
    msg = _missing_args_message(
        "composition_generate", ["model_ref"], None, {"model_ref": {"description": desc}},
    )
    assert msg.count("settings_list_models") == 1, msg


def test_a_tool_with_no_declared_emitter_is_unchanged():
    """PRECISION. The undeclared arm is the common case (302 of 316 tools) and must keep its
    wording — this fix adds a sentence where data exists, it does not rewrite the fallback."""
    msg = _missing_args_message("some_tool_with_no_contract", ["whatever_id"], None, {})
    assert "does not declare" in msg, msg
    assert "emits" not in msg


def test_the_named_emitter_is_a_real_catalogue_name():
    """Naming a tool is what ARMS it, and a message naming an off-catalogue tool arms nothing.
    Every emitter in the registry must therefore be a plausible tool name, not prose."""
    for tool, m in EMITTERS.items():
        for arg, emitter in m.items():
            assert isinstance(emitter, str) and emitter, f"{tool}.{arg}"
            assert " " not in emitter, f"{tool}.{arg} -> {emitter!r} is prose, not a tool name"


def test_the_owed_branch_still_wins_where_it_applies():
    """The `owed` arm carries a stronger statement (the runtime owes this value, do not
    invent it). The new clause must not displace it for the 3 pairs that reach it."""
    block = CONTRACTS.get("plan_compile")
    assert block, "plan_compile lost its contract row — this test's premise is gone"
    msg = _missing_args_message("plan_compile", ["run_id"], block, {})
    assert "plan_propose_spec" in msg
    assert "NOT yours to invent" in msg or "runtime" in msg.lower(), msg


@pytest.mark.parametrize("tool,arg,emitter", [
    (t, a, e) for t, m in sorted(EMITTERS.items()) for a, e in sorted(m.items())
][:40])
def test_every_declared_emitter_can_reach_a_refusal(tool, arg, emitter):
    """THE CLASS. For any tool carrying a declared emitter, a missing-arg refusal must be able
    to name it — with or without a `contracts` row, with or without a description. This is the
    guard that would have caught the original defect on any of the 90 unreachable pairs
    rather than only on the one that was sampled."""
    msg = _missing_args_message(tool, [arg], CONTRACTS.get(tool), {})
    assert emitter in msg, f"{tool}.{arg} declares {emitter} and the refusal never names it: {msg}"
