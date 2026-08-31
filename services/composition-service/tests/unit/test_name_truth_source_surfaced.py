"""`truth_source` must reach the caller, because a proxy that does not announce itself
reads exactly like a verification.

`name_grounding.py` calls this "the field that matters most": with `prompt_proxy` the
draft's names are compared against the DRAFTER'S OWN packed prompt — a self-consistency
observation, not a check against canon. It was computed and then dropped before the
envelope, so no caller could tell the two apart.

Found while interpreting QC-5's drafting run, where `name_grounding` was the ONLY check
with coverage on all three chapters and there was no way to know what it had compared to.
"""
from __future__ import annotations

from app.engine.canon_check import ReflectResult, canon_envelope
from app.engine.name_grounding import audit_names


def _envelope(**kw):
    r = ReflectResult(text="t", **kw)
    return canon_envelope(r)


def test_the_envelope_carries_what_the_names_were_compared_against():
    env = _envelope(name_check_method="capitalised_latin", name_truth_source="prompt_proxy")
    assert env["name_truth_source"] == "prompt_proxy", (
        "the envelope dropped truth_source — a caller cannot tell a canon check from a "
        "self-consistency observation"
    )


def test_glossary_and_proxy_are_distinguishable_in_the_envelope():
    assert _envelope(name_truth_source="glossary")["name_truth_source"] == "glossary"
    assert _envelope(name_truth_source="prompt_proxy")["name_truth_source"] == "prompt_proxy"


def test_the_audit_reports_prompt_proxy_when_no_authored_names_are_given():
    """The fallback is the whole reason the field exists: without `known_names` the
    comparison silently becomes the drafter grading its own homework."""
    audit = audit_names(grounding="Arthur went north.", draft="Arthur met Mira.")
    assert audit.truth_source == "prompt_proxy"


def test_the_audit_reports_glossary_when_authored_names_are_given():
    audit = audit_names(grounding="Arthur went north.", draft="Arthur met Mira.",
                        known_names=["Arthur", "Mira"])
    assert audit.truth_source == "glossary"
