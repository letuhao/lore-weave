"""TOOL DEEP-DIVE `glossary_create_evidence` — R1 answerability is INERT on every resumed turn,
so the moment after a user clicks "approve" is the one moment the surface stops being able to
answer the request it was suspended on.

🔴 MEASURED LIVE 2026-08-23, K=5, batch c-evidence3 (gemma-4-26b via lm_studio), on a throwaway
book whose own seed created the entity and its `occupation` attribute value. The request was:

    "Back up Aldric Vane's role with a passage from the chapter — cite where it says he climbed
     the black stair."

`glossary_create_evidence` DECLARES both "back up" and "cite where", each contiguous in that
sentence, and `answerable_tools` matches it (asserted below). Measured:

  * advertised on the wire for snapshots 2..10 — every pass BEFORE the approval card;
  * ABSENT from snapshots 13..24 — every pass AFTER it, 5 runs of 5;
  * called 0/5. Instead the model went kg_project_create ×4 → kg_add_nodes, on all five runs.

Both surfaces held exactly 41 tools (4 core + 3 frontend + 34 activated). The resume re-seeds
with studio=True, so the composition family (composition_list_outline, composition_motif_get,
composition_arc_template_get, …) displaced the glossary family at an unchanged budget. That
displacement is what R1 exists to overrule: "if the user's words match a tool's own vocabulary,
it is on the wire — whatever the budget, the domain selection or the rail decided."

THE MECHANISM. `_emit_chat_turn(… request_text: str = "")` hands the text to the per-pass
advertise chokepoint, and R1's own docstring says of it: "Empty ⇒ inert". The fresh path passes
`request_text=user_message_content`. `resume_stream_response` does not pass it at all — so it
defaults to "" and the guarantee is dead for the whole remainder of the turn.

Not a narrow miss: the resume already threads `request_text=susp.user_message_content` into the
ONE-OFF `_advertise_discovery_tools` call that builds its first tool_defs, with the comment "A
resume is still answering the ORIGINAL request … Dropping it here would make the post-approval
pass the one surface in the system that cannot answer the question it was suspended on." That
sentence describes exactly what happens on every pass after the first, because the per-pass
chokepoint is reached through `_emit_chat_turn` and never got the argument.

The text has been persisted in `chat_suspended_runs.user_message_content` the whole time —
verified in the store for all six suspends of this batch, 107 chars each, the full prompt. The
data was there; nothing passed it on.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "app" / "services" / "stream_service.py"


def _emit_chat_turn_calls_in(func_name: str) -> list[ast.Call]:
    """Every `_emit_chat_turn(...)` call lexically inside `func_name`.

    AST rather than a substring: `request_text=` appears a dozen times in this file, and a
    substring test would go green on any of them while the resume kept shipping "".
    """
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func_name
    )
    return [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_emit_chat_turn"
    ]


def test_the_resume_hands_the_request_to_the_advertise_chokepoint():
    """🔴 THE DEFECT."""
    calls = _emit_chat_turn_calls_in("resume_stream_response")
    assert calls, "resume_stream_response no longer calls _emit_chat_turn — re-anchor this test"
    for call in calls:
        kwargs = {kw.arg for kw in call.keywords if kw.arg}
        assert "request_text" in kwargs, (
            "resume_stream_response calls _emit_chat_turn WITHOUT request_text, so it defaults "
            "to '' and R1 answerability is inert for the whole resumed turn — the tool whose "
            "own declared words answer the request leaves the wire the moment the user "
            "approves. Measured 5/5 on glossary_create_evidence."
        )


def test_it_is_the_SUSPENDED_run_s_request_and_not_some_other_text():
    """A resume has no new user message; the only right answer is the one that was suspended on,
    which is why it is persisted. Passing anything else (the tool result, the last assistant
    turn) would re-point the guarantee at text the user never typed."""
    for call in _emit_chat_turn_calls_in("resume_stream_response"):
        kw = next((k for k in call.keywords if k.arg == "request_text"), None)
        assert kw is not None
        assert ast.unparse(kw.value) == "susp.user_message_content", (
            "the resume passes something other than the suspended run's own persisted request "
            f"text: {ast.unparse(kw.value)}"
        )


def test_the_FRESH_path_passes_it_too():
    """THE CONTROL. If this ever goes red the defect is not the resume's — R1 is off everywhere,
    and a green resume test would be measuring a guarantee that no longer exists."""
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    passing = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == "_emit_chat_turn"
        and any(k.arg == "request_text" for k in n.keywords)
    ]
    assert len(passing) >= 2, (
        "fewer than two _emit_chat_turn call sites pass request_text — the fresh path is the "
        "control for the resume and both must carry it"
    )


def test_the_words_in_the_measured_request_really_do_reach_this_tool():
    """The link between the mechanism and the live measurement: R1 WOULD have kept the tool on
    the wire, so nothing about this turn is explained by the model failing to be offered a
    match. If this goes red, the live result above has a second cause and the note must change."""
    from app.services.tool_surface import answerable_tools

    td = {
        "type": "function",
        "function": {
            "name": "glossary_create_evidence",
            "description": "Attach an evidence excerpt supporting an attribute value.",
            "parameters": {},
            # verbatim from services/glossary-service/internal/api/pipeline_write_tools.go
            "_meta": {"synonyms": [
                "add a quote supporting this", "attach evidence", "cite where this is stated",
                "back this up with a passage", "cite where", "back up", "quote the passage",
                "attach a quote", "source this from the text",
            ]},
        },
    }
    prompt = ("Back up Aldric Vane's role with a passage from the chapter — "
              "cite where it says he climbed the black stair.")
    assert answerable_tools(prompt, [td]) == {"glossary_create_evidence"}
