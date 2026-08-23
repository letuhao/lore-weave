"""QC-5 — the narrow verification pass that closes `D-QC5-PROSE-JUDGE-FIRES-ON-CONFORMING-PROSE`.

`map_rule_tokens` proves a verdict is ATTRIBUTABLE — that the judge answered about a rule we
actually sent. It cannot prove the verdict is TRUE, and the measured false positives are exactly
the class it cannot catch: they cite a REAL rule id and invent the rule's content, or they
restate the rule as the reason a passage obeying it is a violation.

Measured before this was built, planted-vs-clean on one passage differing by a single name:

    verifier      planted (a real R1 violation)   clean        historical false
    gemma-4-26b   kept 4/4                        dropped 2/2  dropped 14/14
    qwen2.5-7b    kept 4/4                        kept 0/3

Both arms are in the table on purpose: a filter is only a filter if it keeps a true finding AND
drops a false one, and the 7B row is a judge that keeps everything.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from loreweave_llm.errors import LLMError

from app.engine import critic
from app.engine.critic import verify_violations
from app.packer.profile import NEUTRAL

RULES = [{"rule_id": "rule-betrayer", "text": "Lam Trach is the betrayer. No one else is."}]
VIOL = [{"rule_id": "rule-betrayer", "violated": True, "span": "some span", "why": "a claim"}]


class ScriptedJudge:
    """Returns a different reply per call, so the critique and the verification are distinct."""

    def __init__(self, *replies, raises_on=None, status="completed"):
        self._replies = list(replies)
        self._raises_on = raises_on
        self._status = status
        self.calls = []

    async def submit_and_wait(self, **kw):
        self.calls.append(kw)
        if self._raises_on is not None and len(self.calls) == self._raises_on:
            raise LLMError("gateway down")
        content = self._replies[min(len(self.calls) - 1, len(self._replies) - 1)]
        return SimpleNamespace(
            status=self._status,
            result={"messages": [{"role": "assistant", "content": content}]},
        )


def _reply(contradicts, reason="because"):
    return json.dumps({"contradicts": contradicts, "reason": reason})


def _critique_with_one_violation():
    return json.dumps({
        "coherence": 4, "voice_match": 4, "pacing": 4, "canon_consistency": 2,
        "violations": [{"rule_id": critic.rule_token(0), "violated": True,
                        "span": "some span", "why": "a claim"}],
        "craft_notes": [],
    })


@pytest.mark.asyncio
async def test_a_refuted_verdict_is_dropped_and_NAMED():
    judge = ScriptedJudge(_reply(False, "the passage agrees with the rule"))
    kept, dropped = await verify_violations(
        judge, user_id="u", model_source="s", model_ref="m", passage="p",
        violations=VIOL, active_rules=RULES,
    )
    assert kept == []
    assert len(dropped) == 1
    assert "rule-betrayer" in dropped[0], "the drop must name the rule it refuted"
    assert "agrees with the rule" in dropped[0], (
        "the verifier's own words carry the reason — a bare count cannot tell a refuted verdict "
        "from a clean passage, which is the defect this whole envelope exists to avoid"
    )


@pytest.mark.asyncio
async def test_a_confirmed_verdict_SURVIVES():
    """The control arm. Every assertion above is satisfied by a verifier that refuses
    everything — and that verifier would delete real findings while reporting success. The
    measured 7B failure is the mirror of this one, keeping everything."""
    judge = ScriptedJudge(_reply(True, "the passage names a different betrayer"))
    kept, dropped = await verify_violations(
        judge, user_id="u", model_source="s", model_ref="m", passage="p",
        violations=VIOL, active_rules=RULES,
    )
    assert kept == VIOL
    assert dropped == []


@pytest.mark.asyncio
async def test_it_fails_OPEN_when_the_verifier_errors():
    """CC4: advisory must not block, and a verifier that cannot answer has NOT refuted anything.
    Deleting a finding because the second call failed would turn an outage into a clean bill."""
    judge = ScriptedJudge(_reply(False), raises_on=1)
    kept, dropped = await verify_violations(
        judge, user_id="u", model_source="s", model_ref="m", passage="p",
        violations=VIOL, active_rules=RULES,
    )
    assert kept == VIOL and dropped == []


@pytest.mark.asyncio
async def test_an_UNPARSABLE_reply_is_not_a_refutation():
    judge = ScriptedJudge("I think, on balance, maybe?")
    kept, dropped = await verify_violations(
        judge, user_id="u", model_source="s", model_ref="m", passage="p",
        violations=VIOL, active_rules=RULES,
    )
    assert kept == VIOL and dropped == []


@pytest.mark.asyncio
async def test_a_verdict_whose_rule_has_no_text_is_KEPT_not_dropped():
    """An unauditable verdict is not a disproven one, and it must not reach the drop counter —
    that number is read as 'the judge was refuted this many times'."""
    judge = ScriptedJudge(_reply(False))
    kept, dropped = await verify_violations(
        judge, user_id="u", model_source="s", model_ref="m", passage="p",
        violations=[{"rule_id": "not-a-rule-we-sent", "span": "s", "why": "w"}],
        active_rules=RULES,
    )
    assert len(kept) == 1 and dropped == []
    assert judge.calls == [], "an unauditable verdict must not cost an LLM call either"


@pytest.mark.asyncio
async def test_judge_prose_ACTUALLY_CALLS_the_verifier():
    """🔴 The WIRING, not the rule.

    `verify_violations` passing its own tests proves nothing about whether `judge_prose` invokes
    it — a correct filter that nothing calls is the shape this plan has found repeatedly. This
    drives the real entry point and asserts the refusal reaches the envelope.
    """
    judge = ScriptedJudge(_critique_with_one_violation(),
                          _reply(False, "the passage agrees with the rule"))
    crit = await critic.judge_prose(
        judge, user_id="u", model_source="s", model_ref="m", passage="a passage",
        active_rules=RULES, present_facts=[], profile=NEUTRAL,
    )
    assert len(judge.calls) == 2, "the verifier must be a SECOND call, not a re-read of the first"
    assert crit["violations"] == [], "the refuted verdict must not reach the caller"
    assert crit["violations_unverified"] == 1
    assert "agrees with the rule" in crit["violations_unverified_reasons"][0]


@pytest.mark.asyncio
async def test_a_CONFIRMED_verdict_still_reaches_the_caller_through_judge_prose():
    """The wiring's control arm: the pass must not be a filter that empties every critique."""
    judge = ScriptedJudge(_critique_with_one_violation(),
                          _reply(True, "the passage names a different betrayer"))
    crit = await critic.judge_prose(
        judge, user_id="u", model_source="s", model_ref="m", passage="a passage",
        active_rules=RULES, present_facts=[], profile=NEUTRAL,
    )
    assert len(crit["violations"]) == 1
    assert crit.get("violations_unverified", 0) == 0


@pytest.mark.asyncio
async def test_no_violations_costs_no_verifier_call():
    """The common case is a clean passage, and it must not pay for a second round trip."""
    critique = json.dumps({
        "coherence": 4, "voice_match": 4, "pacing": 4, "canon_consistency": 5,
        "violations": [], "craft_notes": [],
    })
    judge = ScriptedJudge(critique)
    crit = await critic.judge_prose(
        judge, user_id="u", model_source="s", model_ref="m", passage="a passage",
        active_rules=RULES, present_facts=[], profile=NEUTRAL,
    )
    assert len(judge.calls) == 1
    assert crit["violations"] == []
    assert crit["violations_unverified"] == 0, (
        "stamped even at zero, like `violations_dropped` beside it — a key that appears only "
        "when non-zero makes a missing field and a clean result the same observation"
    )

@pytest.mark.asyncio
async def test_the_VERIFIER_ROLE_routes_the_audit_to_its_own_model():
    """QC-5 C33 — `ModelRole.CRITIC_VERIFIER`, and that it actually changes who audits.

    C31 measured the two jobs apart: one model kept 4/4 planted violations and 0/3 false ones
    when auditing its OWN output. A book can therefore want breadth from one model and precision
    from another, which is what the seventh role is for. This asserts the routing rather than the
    setting: the critique goes to the critic, the audit goes to the verifier.
    """
    judge = ScriptedJudge(_critique_with_one_violation(), _reply(False, "agrees with the rule"))
    await critic.judge_prose(
        judge, user_id="u", model_source="s", model_ref="critic-model", passage="a passage",
        active_rules=RULES, present_facts=[], profile=NEUTRAL,
        verifier_source="vs", verifier_ref="verifier-model",
    )
    assert judge.calls[0]["model_ref"] == "critic-model"
    assert judge.calls[1]["model_ref"] == "verifier-model", "the audit must go to the verifier"
    assert judge.calls[1]["model_source"] == "vs"


@pytest.mark.asyncio
async def test_no_verifier_configured_FALLS_BACK_to_the_critic():
    """The control arm, and the compatibility guarantee: every book that never sets a verifier
    keeps exactly today's behaviour. A routing change that only worked when configured would
    silently stop auditing for every existing book."""
    judge = ScriptedJudge(_critique_with_one_violation(), _reply(False, "agrees with the rule"))
    await critic.judge_prose(
        judge, user_id="u", model_source="s", model_ref="critic-model", passage="a passage",
        active_rules=RULES, present_facts=[], profile=NEUTRAL,
    )
    assert len(judge.calls) == 2, "the audit must still happen"
    assert judge.calls[1]["model_ref"] == "critic-model"
    assert judge.calls[1]["model_source"] == "s"

