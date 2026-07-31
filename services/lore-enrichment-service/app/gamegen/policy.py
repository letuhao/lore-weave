"""S4 — where the numbers come from, and who is allowed to choose them.

Doc 39 §6. Two axioms carry this stage, and they compose into one shape.

> **`PGN-A5`** — a model may emit CARDINALITY, ORDER, and NAMES THE BOOK
> CONTAINS. **Never MAGNITUDE.**

How many tiers, which is fourth, and what the book calls them are facts a span
supports. How much grinding a tier costs is a balance decision no amount of
reading produces. So every magnitude in the engine schema is answered *here*, by
a human-authored artifact, and never by the interrogation stage — which is why
S3's :func:`~app.gamegen.fold.assert_no_magnitude_leaked` refuses one that tries.

> **`PGN-A15`** — the policy is **System-tier by default** and a book policy
> **NARROWS** it.

v1 declared no tier at all, and the consequence was concrete: a novelist reaching
S4 faces knobs she has no basis to set, no default to narrow, and one complete
plausible example in the design document — so those illustrative numbers become
the platform's de-facto global balance, reviewed by nobody, while every gate
reports a human-authored policy.

That is the ``effective = AND(deploy_allows, user_enables)`` shape the Settings &
Configuration standard already mandates (SET-3: env/System is a **ceiling** the
user narrows within, never a per-user knob). It converts S4 from *authorship* into
**review of a diff against a shipped baseline** — a decision a novelist can
actually make.

## The shape, and what makes each half refusable

A policy maps every **magnitude path** to a :class:`Band` — ``[min, max]`` plus a
``default`` inside it.

* **Coverage is ASSERTED, not assumed** (:func:`assert_covers_magnitudes`),
  against ``contracts/progression-schema.json`` — the same generated artifact the
  brief is checked against, for the same reason: a magnitude with no band is a
  number S5 would have to invent, and a band for a non-magnitude is a knob the
  engine never reads. Set equality, both directions.
* **Narrowing is CHECKED** (:func:`narrow`). A book band must be a subset of its
  System parent's. A book policy that *widens* is refused **by path**, which is
  the whole of `PGN-A15`: without it, "narrow" is a word in a document and a book
  policy is just a second global policy with extra steps.
* **A book policy cannot exist without a parent.** Enforced in the schema, not
  only here — you may narrow a shipped baseline; you may not author from scratch.

## `PGN-A16` — fixed-point saturating integers, and no floats anywhere

Every band value is an ``int``. A float would make S5's output depend on IEEE
rounding, and T4 (*same inputs → same artifact*) would hold only on one
platform's libm. Milli-units (``*_milli``) are how the schema already carries
fractional rates, so nothing is lost by refusing floats — and :func:`_check_int`
refuses ``bool`` explicitly, because ``isinstance(True, int)`` is True in Python
and ``True`` would otherwise be a legal rate of 1.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from app.gamegen.brief import BriefCoverageError, load_contract

__all__ = [
    "Band",
    "Policy",
    "PolicyError",
    "assert_covers_magnitudes",
    "magnitude_paths",
    "narrow",
    "policy_hash",
]

_DOMAIN = b"lw.gamegen.policy.v1"

TIERS = ("system", "book")


class PolicyError(ValueError):
    """A policy is inadmissible. Never a warning: an unusable policy that reaches
    S5 becomes engine defaults with a human-authored-policy label on them."""


@dataclass(frozen=True)
class Band:
    """The allowed range for one magnitude, plus the default inside it.

    A **range** and not a single value, because that is what makes narrowing
    meaningful: the System tier ships what a book MAY choose, the book chooses
    within it, and the two are different statements. A System policy of bare
    values would leave a book author with nothing to narrow and no way to signal
    that a knob is deliberately fixed — which she can still do here, with
    ``min == max``.
    """

    min: int
    max: int
    default: int

    def __post_init__(self) -> None:
        for name in ("min", "max", "default"):
            _check_int(getattr(self, name), name)
        if self.min > self.max:
            raise PolicyError(f"band [{self.min}, {self.max}] is inverted")
        if not self.min <= self.default <= self.max:
            raise PolicyError(
                f"default {self.default} is outside its own band [{self.min}, {self.max}]. "
                f"A default nobody can reach is the silent-drop shape one tier down: every "
                f"check green, and S5 emitting a number no reviewer could have chosen."
            )

    def contains(self, other: "Band") -> bool:
        return self.min <= other.min and other.max <= self.max

    def as_json(self) -> dict[str, int]:
        return {"min": self.min, "max": self.max, "default": self.default}


def _check_int(v: Any, where: str) -> None:
    # bool BEFORE int: isinstance(True, int) is True, so without this arm `True`
    # is a legal rate of 1 and a policy typo becomes a balance decision.
    if isinstance(v, bool) or not isinstance(v, int):
        raise PolicyError(
            f"{where}={v!r} is not an integer. `PGN-A16` is fixed-point saturating "
            f"integers: a float would make S5's output depend on IEEE rounding and T4 "
            f"(same inputs -> same artifact) would hold only on one platform's libm. "
            f"Fractional rates are carried in milli-units by the schema itself."
        )


@dataclass(frozen=True)
class Policy:
    element_kind: str
    schema_fingerprint: str
    tier: str
    policy_version: int
    bands: Mapping[str, Band]

    def __post_init__(self) -> None:
        if self.tier not in TIERS:
            raise PolicyError(f"tier {self.tier!r} is not one of {TIERS}")


def magnitude_paths(contract: dict | None = None) -> set[str]:
    """The positions a policy MUST band, read from the engine's own schema export.

    Not re-derived here, for the reason ``brief.py`` states at length: a second
    implementation of a Rust type is a mirror nothing forces to agree (`CPL-A2`).
    """
    c = contract or load_contract()
    return {p["path"] for p in c["paths"] if p["askable"] == "magnitude"}


def assert_covers_magnitudes(policy: Policy, contract: dict | None = None) -> None:
    """**The check that can fail.** Set equality, both directions.

    Deliberately the same mechanism as the brief's coverage assertion, because it
    is the same failure: a required position with no producer. The two halves
    fail differently and both matter —

    * a magnitude with **no band** is a number S5 must invent, and the engine's
      default would then wear the policy's signature;
    * a band for a path the engine does **not** call a magnitude is a knob nothing
      reads, and it will be tuned by someone watching for an effect that cannot
      arrive.
    """
    c = contract or load_contract()
    if policy.schema_fingerprint != c["fingerprint"]:
        raise PolicyError(
            f"policy for {policy.element_kind!r} was authored against schema fingerprint "
            f"{policy.schema_fingerprint[:12]}… and the engine's is {c['fingerprint'][:12]}…. "
            f"The schema MOVED - a magnitude was added, removed, or reclassified. Re-read "
            f"the contract and re-band; the fingerprint is what makes that a loud event."
        )

    want = magnitude_paths(c)
    have = set(policy.bands)

    missing = sorted(want - have)
    if missing:
        raise PolicyError(
            f"policy for {policy.element_kind!r} bands nothing for {missing}. Every "
            f"MAGNITUDE needs a band, or S5 invents the number and the engine's default "
            f"ships wearing this policy's signature."
        )
    extra = sorted(have - want)
    if extra:
        raise PolicyError(
            f"policy for {policy.element_kind!r} bands {extra}, which the engine does not "
            f"class as a magnitude. Refused rather than ignored: a knob nothing reads gets "
            f"tuned by someone watching for an effect that cannot arrive."
        )


def narrow(*, parent: Policy, child_bands: Mapping[str, Band], book_version: int) -> Policy:
    """Produce a **book** policy that narrows a **System** parent.

    This function is `PGN-A15`. Without the subset check, "narrow" is a word in a
    design document and a book policy is a second global policy with extra steps.

    Rules, each refused **by path** so the message names the knob:

    * the parent must be System tier — narrowing a narrowing would let a chain
      widen one step at a time while every individual step looked legal;
    * a child band must be **contained** in the parent's;
    * a child may band a **subset** of the parent's paths (the rest inherit), and
      may never introduce a path the parent does not have — that would be
      authorship, not narrowing.
    """
    if parent.tier != "system":
        raise PolicyError(
            f"parent policy is tier {parent.tier!r}; only a System policy may be narrowed. "
            f"Narrowing a narrowing lets a chain widen one step at a time with every "
            f"individual step looking legal."
        )

    unknown = sorted(set(child_bands) - set(parent.bands))
    if unknown:
        raise PolicyError(
            f"book policy introduces {unknown}, which the System policy does not band. "
            f"A book NARROWS a shipped baseline; introducing a knob is authorship, and it "
            f"is how a per-book override quietly becomes a second global policy."
        )

    widened: list[str] = []
    for path, band in child_bands.items():
        if not parent.bands[path].contains(band):
            p = parent.bands[path]
            widened.append(
                f"{path}: book [{band.min}, {band.max}] is not inside system [{p.min}, {p.max}]"
            )
    if widened:
        raise PolicyError(
            "book policy WIDENS the System baseline: "
            + "; ".join(widened)
            + ". `PGN-A15` is effective = AND(deploy_allows, user_enables) - the System tier "
            "is a ceiling, not a suggestion."
        )

    merged = dict(parent.bands)
    merged.update(child_bands)
    return Policy(
        element_kind=parent.element_kind,
        schema_fingerprint=parent.schema_fingerprint,
        tier="book",
        policy_version=book_version,
        bands=merged,
    )


def policy_hash(policy: Policy) -> str:
    """The address S5 stamps beside ``structure_hash`` for T2.

    Covers the tier and the fingerprint as well as the bands: the same numbers
    shipped as a System baseline and as one book's narrowing are **different
    facts about who chose them**, and T2 is *"I can tell where a number came
    from"*.
    """
    h = hashlib.blake2b(digest_size=32)
    h.update(_DOMAIN)
    for part in (policy.element_kind, policy.schema_fingerprint, policy.tier):
        b = part.encode("utf-8")
        h.update(len(b).to_bytes(4, "big"))
        h.update(b)
    h.update(policy.policy_version.to_bytes(4, "big"))
    body = {p: policy.bands[p].as_json() for p in sorted(policy.bands)}
    h.update(
        json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    return h.hexdigest()


def body_json(policy: Policy) -> dict[str, Any]:
    """The stored form. Sorted so the bytes are canonical without a second pass."""
    return {p: policy.bands[p].as_json() for p in sorted(policy.bands)}


def from_body(
    *, element_kind: str, schema_fingerprint: str, tier: str, policy_version: int, body: Mapping
) -> Policy:
    return Policy(
        element_kind=element_kind,
        schema_fingerprint=schema_fingerprint,
        tier=tier,
        policy_version=policy_version,
        bands={p: Band(**b) for p, b in body.items()},
    )
