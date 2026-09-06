"""TOOLV2 LOOP #277 — focus paths invented by the model and passed straight to the refiner.

`plan_interpret_feedback` genuinely interprets. Four varied notes produced four distinct readings,
and the control — "Yes, that looks right to me." — correctly came back with confidence 0.4 and no
paths at all, which is the strongest evidence the model is reading the input rather than answering
from a template.

The `focus_paths` were the problem. They feed `plan_apply_revision(focus_paths=...)`, so a path
that does not resolve focuses a refine on nothing. Measured on a live run:

    "magic system inconsistent"  -> ['mechanics.magic_system', 'events[*].rules_applied']
    "scrap the second act"       -> ['events[act_2]', 'layers.characters[act_2]', ...]

`mechanics.magic_system` cannot resolve — the spec keeps mechanics under `layers`, and there is no
top-level key of that name. `events[act_2]` and `layers.characters[act_2]` are string subscripts
into arrays. And the LLM branch used `extract_json_object(content)` verbatim, while
`interpret_rules` — its own fallback, three lines below in the same function — already filtered its
paths to those starting `events`/`layers`. The guard was standing next to the path that skipped it.

Then the measurement that reframed it. `build_spec_index` derives entirely from the spec:
`layers.characters[0]` needs a non-empty characters array, mechanics a non-empty list, events an
`arc_2` arc. For the run under test the index held ZERO entries — so `search_index` could never
return a hit, `interpret_rules` could never produce a path, and every path the tool had been
returning was ungrounded by construction. Across the instance, 64 of 321 runs have a non-empty
index; the rest can ground nothing.

The fix validates the model's paths against the SAME index the branch already builds for the
prompt, and falls back to the index's own top hits when nothing the model named is real — so a
refine still gets somewhere to look rather than an empty focus.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "services" / "plan_forge_service.py"


def _llm_branch() -> str:
    body = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = body.index("out = extract_json_object(content)")
    return body[start: body.index("async def find_missing_material", start)]


def test_the_models_paths_are_checked_against_the_spec_index():
    fn = _llm_branch()
    assert 'real_paths = {e["path"] for e in index if e.get("path")}' in fn, (
        "the LLM branch uses the model's focus_paths verbatim again; they feed "
        "plan_apply_revision and a path that does not resolve focuses a refine on nothing"
    )
    assert "kept = [p for p in proposed if p in real_paths]" in fn


def test_an_all_invented_set_falls_back_to_a_grounded_hit():
    """Dropping every path would leave the refine with no target at all. The index's own top
    hits are the grounded alternative — measured: ['mechanics.magic_system', 'events[act_2]',
    'layers.characters[act_2]'] becomes ['layers.characters[0]']."""
    fn = _llm_branch()
    assert "if proposed and not kept:" in fn
    assert 'kept = [h["path"] for h in hits[:2] if h.get("path")]' in fn


def test_an_empty_model_answer_stays_empty():
    """`proposed and not kept` — the fallback fires only when the model NAMED something and none
    of it was real. A model that honestly returned no paths (the 'yes, that looks right' case)
    must not have paths invented for it."""
    fn = _llm_branch()
    assert "if proposed and not kept:" in fn, (
        "the guard must be conditional on `proposed`, or an honest empty answer gets filled in"
    )


def test_it_reuses_the_index_already_built_for_the_prompt():
    """Building a second index here would double the work and could diverge from the one the
    model was actually shown."""
    body = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    branch_start = body.index("index = build_spec_index(spec, section_map)")
    check_start = body.index('real_paths = {e["path"] for e in index')
    assert branch_start < check_start, "the check must reuse the index built above it"
    assert body.count("index = build_spec_index(spec, section_map)", branch_start, check_start) == 1


def test_the_rules_fallback_keeps_its_own_filter():
    """interpret_rules filtered its paths before this fix and is still the branch taken for
    handoff/recheck/complaint. Removing its filter would reopen the hole from the other side."""
    interp = (SRC.parents[1] / "engine" / "plan_forge" / "interpret.py").read_text(encoding="utf-8")
    assert 'h["path"].startswith("events") or h["path"].startswith("layers")' in interp
