"""S6 — no model is silently its own judge. One place that decides who judges.

The rule
--------
A critique is only worth anything if a DIFFERENT model produces it. A model grading its own
prose is a self-witness, and this repo has paid for that shape repeatedly: a check whose
verifier shares a source of truth with the thing it verifies cannot fail in the direction that
matters.

So the drafter's own model is refused as a critic. That much was already true.

What was NOT true, and is what this module is for
------------------------------------------------
The rule was hand-rolled at **seven** sites in `routers/engine.py` — six copies of

    distinct = bool(c_ref and c_src and str(c_ref) != str(body.model_ref))

plus a seventh written inverted, as the `if not critic_ref or ... or ==` guard on the critique
endpoint. Six identical copies of a predicate is the exact shape `canon_envelope()` was
extracted from in the POST-RUN REVIEW, and the reason that mattered there applies here: when a
field was added to the envelope it reached all six copies and `verdict` reached none. A rule
that lives in seven places gets amended in six.

And the seventh copy is where the real defect is. It collapses TWO different states into one
sentence — *"critique skipped: no distinct critic model configured"*:

  · **NOT_CONFIGURED** — the author never set a critic. Nothing is wrong; the blocking tier is
    simply off, and they may not know it exists.
  · **SAME_AS_DRAFTER** — the author DID set one, and it is the model already writing the prose,
    so it was refused. This is a misconfiguration with a fix, and it reads identically to the
    case above.

Those need different words because they need different actions, and neither is "an outage".
Same distinction `CheckStatus` exists for one layer up — `NO_RULES` (nothing to check) versus a
gap (the check did not run). Collapsing them is what makes a permanently-amber guard that an
author has no way to clear, which is the failure S1 was written to end.

`status` is therefore the point of this module, not `distinct`. A caller that only needs the
boolean reads `.distinct`; a caller that has to TELL SOMEBODY reads `.status`.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

__all__ = [
    "CriticStatus", "CriticResolution", "resolve_critic", "resolve_critic_refs",
    "resolve_critic_verified",
]


class CriticStatus(str, Enum):
    """Why this generation does — or does not — get an independent judge."""

    #: A distinct critic model is configured and will judge.
    CONFIGURED = "configured"
    #: No critic set. The blocking tier is OFF, and the author has not been told.
    NOT_CONFIGURED = "not_configured"
    #: A critic IS set and it is the drafter's own model, so it was refused. A
    #: misconfiguration with a concrete fix — never the same message as the case above.
    SAME_AS_DRAFTER = "same_as_drafter"
    #: A critic ref is present without its source (or vice versa) — a half-written setting.
    #: Kept distinct from NOT_CONFIGURED because "you never set one" and "the one you set is
    #: unusable" are different sentences, and the second one is a bug report.
    INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class CriticResolution:
    """Who judges, and why — resolved once, read by every caller."""

    status: CriticStatus
    #: Only ever non-None when `status is CONFIGURED`. A caller cannot accidentally use the
    #: refused model: the refusal is expressed by BLANKING the fields, not by a flag the
    #: caller has to remember to check.
    source: str | None = None
    ref: str | None = None
    #: Did anything confirm that the critic is a DIFFERENT MODEL, rather than merely a
    #: different row?
    #:
    #: `None`  — not attempted (the ref-only comparison; no resolver was supplied).
    #: `True`  — both refs resolved to a provider identity and they differ.
    #: `False` — a resolver was supplied and could not answer, so the refs differ and the
    #:           MODELS are unknown.
    #:
    #: `False` deliberately does NOT flip `distinct` to False. Switching the blocking tier
    #: off whenever provider-registry is briefly unreachable would be a new outage mode, and
    #: it would be strictly worse than the state before this field existed. Same decision, and
    #: the same reason, as `PanelSafety.exclusion_unverified` keeping `safe` True: a flag that
    #: is false on every ordinary run stops being read, and then the real case arrives wearing
    #: the same colour.
    identity_verified: bool | None = None

    @property
    def distinct(self) -> bool:
        """True ⇒ an independent model will judge. The predicate the seven sites hand-rolled."""
        return self.status is CriticStatus.CONFIGURED


def resolve_critic(settings: Mapping[str, Any] | None, drafter_ref: Any) -> CriticResolution:
    """Decide who critiques this generation, from a Work's settings blob."""
    sdict = settings or {}
    return resolve_critic_refs(
        sdict.get("critic_model_source"), sdict.get("critic_model_ref"), drafter_ref
    )


def resolve_critic_refs(src: Any, ref: Any, drafter_ref: Any) -> CriticResolution:
    """The same decision from ALREADY-RESOLVED refs rather than a settings blob.

    This overload exists because the rule had an EIGHTH copy that the S6 sweep missed.
    `canon_reflect` receives `judge_source`/`judge_ref` that a router has already filtered,
    and re-derived the predicate itself:

        distinct = bool(judge_ref and judge_source and str(judge_ref) != str(drafter_ref))

    Harmless the day it was written — the caller blanks the refs when they are not distinct,
    so the re-check agreed — and it is exactly how the seventh copy drifted: a restatement
    that agrees until one side changes. Found by an audit, not by the guard, because the guard
    scanned one FILE.

    Compared as STRINGS because the two sides arrive differently typed — a setting comes out of
    JSONB and a drafter ref off a request body or a job input, so one may be a `UUID` and the
    other its text. An identity check between a `UUID` and its own `str` is False, which would
    let a model judge itself while every test using matching types stayed green.
    """
    if not ref and not src:
        return CriticResolution(CriticStatus.NOT_CONFIGURED)
    if not ref or not src:
        return CriticResolution(CriticStatus.INCOMPLETE)
    if drafter_ref is not None and str(ref) == str(drafter_ref):
        return CriticResolution(CriticStatus.SAME_AS_DRAFTER)
    return CriticResolution(CriticStatus.CONFIGURED, source=str(src), ref=str(ref))


async def resolve_critic_verified(
    settings: Mapping[str, Any] | None,
    drafter_source: Any,
    drafter_ref: Any,
    identity_of: Callable[[str, str], Awaitable[str | None]],
) -> CriticResolution:
    """The same decision, made against WHICH MODEL each ref actually is.

    The defect this closes
    ----------------------
    Everything above compares `user_model_id`s. A `user_model_id` identifies a ROW in one
    user's model registry, not a model — the same weights reached through two BYOK credentials
    are two rows. So a user picks one as drafter and the other as critic, the ids differ, the
    rule answers CONFIGURED, and the model grades its own prose: the exact failure this policy
    is named for, one level below where it was looking.

    Not hypothetical, and not rare. Measured on the dev stack 2026-08-02:

        lm_studio::google/gemma-4-26b-a4b-qat   5 active user_models rows
        ollama::gemma3:12b                      5
        lm_studio::text-embedding-bge-m3        6

    — and the first of those is the model `scripts/dev-model.py` resolves for chat, i.e. the
    default drafter. Any two of its five rows pass the ref comparison.

    Identity is `(provider_kind, provider_model_name)` and deliberately excludes the endpoint:
    two hosts serving the same weights are the same judge, because self-grading is a property
    of the model and not of the box it runs on.

    Degrading
    ---------
    The ref comparison runs FIRST and needs no network, so the same-row case is still caught
    when provider-registry is down. When the resolver cannot answer, the result stays
    CONFIGURED with `identity_verified=False` — see that field for why this does not fail
    closed. It is never upgraded to "verified" on a partial answer: a `None` from either side
    means unknown, not different.
    """
    base = resolve_critic(settings, drafter_ref)
    if base.status is not CriticStatus.CONFIGURED:
        # Nothing to verify: there is no critic, or it was already refused by the cheap check.
        return base
    if drafter_source is None or drafter_ref is None:
        # The caller does not know its own drafter well enough to ask. Not a refusal — the
        # ref comparison already passed — but not a verification either.
        return replace(base, identity_verified=False)

    critic_identity = await identity_of(str(base.source), str(base.ref))
    drafter_identity = await identity_of(str(drafter_source), str(drafter_ref))
    if critic_identity is None or drafter_identity is None:
        return replace(base, identity_verified=False)
    if critic_identity == drafter_identity:
        # Two rows, one model. Fields blanked exactly as the ref-level refusal blanks them, so
        # a caller that ignores `.distinct` still cannot send the refused model anywhere.
        return CriticResolution(CriticStatus.SAME_AS_DRAFTER, identity_verified=True)
    return replace(base, identity_verified=True)
