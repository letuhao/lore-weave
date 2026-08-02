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

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

__all__ = ["CriticStatus", "CriticResolution", "resolve_critic"]


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

    @property
    def distinct(self) -> bool:
        """True ⇒ an independent model will judge. The predicate the seven sites hand-rolled."""
        return self.status is CriticStatus.CONFIGURED


def resolve_critic(settings: Mapping[str, Any] | None, drafter_ref: Any) -> CriticResolution:
    """Decide who critiques this generation.

    `settings` is the Work's settings blob; `drafter_ref` is the model writing the prose.

    Compared as STRINGS because the two sides arrive differently typed — the setting comes out
    of JSONB and the drafter ref off a request body or a job input, so one may be a `UUID` and
    the other its text. An identity check between a `UUID` and its own `str` is False, which
    would let a model judge itself while every test using matching types stayed green.
    """
    sdict = settings or {}
    src = sdict.get("critic_model_source")
    ref = sdict.get("critic_model_ref")

    if not ref and not src:
        return CriticResolution(CriticStatus.NOT_CONFIGURED)
    if not ref or not src:
        return CriticResolution(CriticStatus.INCOMPLETE)
    if drafter_ref is not None and str(ref) == str(drafter_ref):
        return CriticResolution(CriticStatus.SAME_AS_DRAFTER)
    return CriticResolution(CriticStatus.CONFIGURED, source=str(src), ref=str(ref))
