"""Drift gate — reasoning wire fields have exactly ONE producer.

This file exists because the rule was already written down and still drifted **16 times**.

`loreweave_llm.reasoning.reasoning_fields` carries a docstring saying it "replaces translation's
`thinking_llm_fields` + composition's inline copies". Every service named in that sentence adopted
it except composition, the one it named specifically. What grew instead was three dialects:

  1. 13 hand-copied `_NO_THINK = {...}` constants + 3 inline literals + 4 cross-module imports of
     another engine module's PRIVATE constant;
  2. 9 hand-rolled collapses in the router (`None if passthrough else effort`), each of which
     silently dropped `chat_template_kwargs`;
  3. 3 more re-derives in the worker, reading the same job row a different way.

They disagreed on the one case that mattered. `select.py` read a missing effort as "suppress";
`cowrite.stream_draft` read it as "send nothing". Same model, same scene: the auto path produced
prose and the Generate button produced an empty draft, 800 output tokens billed, reported as
`completed`.

A rule with no gate is a rule that drifts. These checks are AST-based, so a comment or a docstring
discussing the fields (this file is full of them) can never trip them — only real code can. And
each detector is exercised against synthetic offending source below, because a gate that has never
gone red is indistinguishable from one that cannot.
"""

from __future__ import annotations

import ast
import pathlib

from loreweave_llm import ReasoningDirective, no_thinking_fields, reasoning_fields

from app.reasoning import wire_fields

APP = pathlib.Path(__file__).resolve().parents[2] / "app"
SOURCES = sorted(APP.rglob("*.py"))


def _trees():
    for path in SOURCES:
        yield path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


# ── detectors (shared by the real scan and the self-test) ──

def hand_built_wire_field(tree: ast.AST) -> list[int]:
    """Lines where a dict literal names `chat_template_kwargs` — i.e. someone rebuilt the wire
    dict instead of calling the producer. That is how a copy is born."""
    return [
        key.lineno
        for node in ast.walk(tree) if isinstance(node, ast.Dict)
        for key in node.keys
        if isinstance(key, ast.Constant) and key.value == "chat_template_kwargs"
    ]


def local_suppressor(tree: ast.AST) -> list[int]:
    """Lines defining/importing a local thinking-suppressor constant. ALL-CAPS is the
    discriminator: the copies were `_NO_THINK` / `_NO_THINK_CACHE`, while the SDK's producer is
    the lower-case callable `no_thinking_fields` that every module SHOULD import."""
    def is_copy(name: str) -> bool:
        return "NO_THINK" in name and name == name.upper()

    hits: list[int] = []
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
        hits += [t.lineno for t in targets if is_copy(t.id)]
        if isinstance(node, ast.ImportFrom):
            # importing the SSOT from the SDK is the point; importing a suppressor out of a
            # sibling app module is the cross-package reach that spread the copies.
            from_sdk = (node.module or "").startswith("loreweave_llm")
            for alias in node.names:
                if is_copy(alias.name) or (not from_sdk and "no_thinking" in alias.name.lower()):
                    hits.append(node.lineno)
    return hits


def bare_effort_parameter(tree: ast.AST) -> list[int]:
    """Lines declaring a `reasoning_effort` parameter — the defect in structural form. A string
    CANNOT carry `chat_template_kwargs`, so every path threading one applies half the decision.
    Pass the resolved `ReasoningDirective`."""
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = node.args
            if any(arg.arg == "reasoning_effort"
                   for arg in [*a.posonlyargs, *a.args, *a.kwonlyargs]):
                hits.append(node.lineno)
    return hits


DETECTORS = {
    "hand-built wire dict": hand_built_wire_field,
    "local suppressor constant": local_suppressor,
    "bare effort parameter": bare_effort_parameter,
}


# ── the real scan ──

def test_the_app_has_enough_sources_to_make_this_gate_meaningful():
    """A gate that silently scans nothing passes forever. Pin the floor."""
    assert len(SOURCES) > 50, f"only found {len(SOURCES)} modules under {APP} — path drifted?"


def test_composition_has_exactly_one_producer_of_reasoning_wire_fields():
    offenders: list[str] = []
    for path, tree in _trees():
        for label, detect in DETECTORS.items():
            offenders += [f"{path.relative_to(APP)}:{ln} [{label}]" for ln in detect(tree)]
    assert not offenders, (
        "reasoning wire fields must come from loreweave_llm (no_thinking_fields() / "
        "reasoning_fields()) or app.reasoning.wire_fields(), and the resolved ReasoningDirective "
        f"must be threaded instead of a bare effort string. Found: {offenders}"
    )


def test_each_detector_actually_fires_on_the_shape_it_bans():
    """The gate must be able to go red. Each of these is a real historical shape."""
    offending = {
        "hand-built wire dict": 'x = {"reasoning_effort": "none", '
                                '"chat_template_kwargs": {"thinking": False}}\n',
        "local suppressor constant": '_NO_THINK = {"reasoning_effort": "none"}\n',
        "bare effort parameter": 'def draft(*, reasoning_effort: str | None = None): ...\n',
    }
    for label, src in offending.items():
        assert DETECTORS[label](ast.parse(src)), f"{label!r} detector missed its own example"
    # ...and the SANCTIONED shapes must stay green, or the gate would just block the fix.
    clean = (
        "from loreweave_llm import no_thinking_fields\n"
        "from app.reasoning import wire_fields\n"
        "def draft(*, reasoning=None):\n"
        "    return {'max_tokens': 10, **wire_fields(reasoning), **no_thinking_fields()}\n"
    )
    tree = ast.parse(clean)
    for label, detect in DETECTORS.items():
        assert not detect(tree), f"{label!r} detector false-positives on the correct pattern"


# ── the seam itself behaves as the gate above assumes ──

def test_wire_fields_suppresses_when_no_directive_was_resolved():
    """The asymmetry that fixes the incident: a MISSING directive is not a licence to send
    nothing. Nothing-sent means the model's own chat template decides, and when the platform has
    misclassified it, that costs a whole output budget and returns silence."""
    assert wire_fields(None) == no_thinking_fields()
    assert wire_fields(None)["reasoning_effort"] == "none"
    assert wire_fields(None)["chat_template_kwargs"] == {"thinking": False, "enable_thinking": False}


def test_wire_fields_still_omits_for_a_self_orchestrating_model():
    """Silence is correct in exactly one case, and it must survive the fix above."""
    adaptive = ReasoningDirective(effort=None, passthrough=True, source="adaptive")
    assert wire_fields(adaptive) == {}


def test_wire_fields_is_a_pass_through_to_the_sdk_for_a_real_directive():
    """composition must not develop its own opinion about the mapping — that is the SDK's job."""
    for effort in ("none", "low", "medium", "high"):
        d = ReasoningDirective(effort=effort, passthrough=False, source="user")  # type: ignore[arg-type]
        assert wire_fields(d) == reasoning_fields(d)
        assert wire_fields(d)["reasoning_effort"] == effort
