"""Teeth for `judge-resolution-gate.py`.

The gate's own first draft could not catch the defect it was written for: it keyed on the words
"critic"/"judge" appearing in a comparison operand, and the historical copy reads
`str(c_ref) != str(body.model_ref)`. `c_ref` contains neither word. So the first two tests here
are the two real wordings, and they exist because a name-keyed detector passed its author's
review and failed the moment it met the actual source.
"""
from __future__ import annotations

import ast
import importlib.util
import pathlib
import sys

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "jrg", pathlib.Path(__file__).resolve().parent / "judge-resolution-gate.py"
)
jrg = importlib.util.module_from_spec(_SPEC)
# Registered before exec for the same reason `test_injection_coverage_lint` does it: a
# `@dataclass` under `from __future__ import annotations` resolves its field types through
# `sys.modules[cls.__module__]`, and a collection-time AttributeError aborts the whole batch.
sys.modules[_SPEC.name] = jrg
_SPEC.loader.exec_module(jrg)


# ── the rule may be stated in exactly one place ───────────────────────────────────────────

@pytest.mark.parametrize("src", [
    # the seven copies in routers/engine.py, verbatim in shape
    'distinct = bool(c_ref and c_src and str(c_ref) != str(body.model_ref))',
    # the EIGHTH, in canon_reflect, which an audit found and no guard did
    'distinct = bool(judge_ref and judge_source and str(judge_ref) != str(drafter_ref))',
    # and the same rule written the other way round
    'if str(drafter_ref) == str(critic_ref):\n    pass',
])
def test_a_re_derivation_of_the_distinctness_rule_is_CAUGHT(src):
    assert jrg.rederivations(ast.parse(src)), (
        "this is the shape the rule had at eight sites; a gate that misses it is decoration"
    )


@pytest.mark.parametrize("src", [
    'if critic_status == "not_configured":\n    pass',   # a status against a literal
    'if len(refs) == count:\n    pass',                  # neither side is a ref
    'if res.verdict != prior.verdict:\n    pass',        # two verdicts, not two models
    'if name == other_name:\n    pass',
])
def test_a_comparison_that_is_NOT_the_rule_is_left_alone(src):
    assert not jrg.rederivations(ast.parse(src))


# ── who counts as carrying a judge ────────────────────────────────────────────────────────

def test_a_judge_passed_by_KEYWORD_is_seen():
    """`worker/operations.py` declares no `judge_ref` parameter — it passes one.

    That call is the unattended path, and it is where the DRAFTER's own refs arrive when no
    critic is configured (`judge_source=critic_source or model_source`). A reading that only
    looked at parameter lists would have left the riskiest caller out of the denominator.
    """
    assert jrg.carries_a_judge(ast.parse('f(judge_source=critic_source or model_source)'))


def test_building_a_judge_request_counts():
    assert jrg.carries_a_judge(ast.parse('req = build_judge_request(msgs, usage_purpose="x", '
                                         'extractor="y")'))


def test_an_unrelated_module_does_not():
    assert not jrg.carries_a_judge(ast.parse('def f(a, b):\n    return a + b\n'))


# ── the delegation chain cannot end in nobody ─────────────────────────────────────────────

def test_every_DELEGATES_row_points_at_a_module_that_exists_and_resolves():
    for module, upstream in jrg.DELEGATES.items():
        p = jrg.ROOT / upstream
        assert p.is_file(), f"{module} delegates to {upstream}, which does not exist"
        tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        assert jrg.resolves(tree) or upstream in jrg.POLICY_MODULES or upstream in jrg.DELEGATES, (
            f"{module} delegates to {upstream}, which neither resolves nor delegates — a chain "
            f"that ends in nobody is how the eighth copy survived"
        )


def test_no_DELEGATES_row_is_stale():
    """A row for a module that no longer carries a judge is a live exemption for nothing."""
    _problems, carriers = jrg.audit()
    stale = sorted(set(jrg.DELEGATES) - set(carriers))
    assert stale == [], f"DELEGATES rows for modules that carry no judge: {stale}"


def test_every_NON_JUDGE_COMPARES_row_still_has_a_comparison():
    for rel in jrg.NON_JUDGE_COMPARES:
        p = jrg.ROOT / rel
        assert p.is_file(), f"{rel} does not exist"
        found = jrg.rederivations(ast.parse(p.read_text(encoding="utf-8", errors="ignore")))
        assert found, f"{rel} is exempted from a comparison it no longer makes"


# ── the live repo ─────────────────────────────────────────────────────────────────────────

def test_the_repo_states_the_rule_in_one_place():
    problems, carriers = jrg.audit()
    assert problems == [], "\n".join(problems)
    assert carriers, "zero judge-carrying modules found — the gate would pass vacuously"
