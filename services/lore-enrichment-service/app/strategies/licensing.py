"""Source-LICENSING gate for the re-cook strategy (RAID C17 — the C17-specific
safety surface).

Re-cook (technique (d), P3) takes REAL history / news / reference material and
re-contextualizes it into the 商周 / 封神演义 fictional setting. Unlike the
public-domain demo corpora (山海经, 封神演义, Shang–Zhou history), modern / news
material is NOT public-domain and carries a copyright / licensing liability. So
re-cook MUST refuse to consume any source that is not licensed or public-domain.

This module is the licensing check. It is **default-deny** (the conservative,
H0/cost-discipline-aligned posture, Q-R2 + the C17 brief):

  * a source is ADMISSIBLE only if its license status is exactly
    :attr:`LicenseStatus.PUBLIC_DOMAIN` or :attr:`LicenseStatus.LICENSED`;
  * anything else — ``unlicensed`` / ``copyrighted`` / ``restricted`` / ``unknown``
    / a missing / blank / unrecognised license value — is REFUSED (raises
    :class:`UnlicensedSourceError`), the source is excluded from the re-cook
    corpus, and the re-cook of that source is refused + escalated;
  * the allowlist is allow-by-PRESENCE-of-an-explicit-admissible-status, NOT
    allow-by-ABSENCE: a missing license is ``UNKNOWN`` → refused (you cannot get
    admitted by simply not declaring a license).

The check is applied at BOTH ends (defence in depth, per the brief):
  * **corpus-admission** — when a re-cook job resolves the source corpus it will
    re-cook from, the corpus's license is checked first; an inadmissible corpus
    is refused before any retrieval / generation happens;
  * **fact-emit** — each grounding ref a re-cooked fact cites is re-checked at
    emit time, so even if a corpus slipped through (it cannot, but defence in
    depth) an unlicensed grounding source can never reach an emitted fact.

NO model names, NO I/O here — this is a pure policy module. The license VALUE for
a corpus is read from ``source_corpus.license`` (the C2/C10 column) by an injected
lookup seam the strategy wires; this module only DECIDES admissibility from a
status value, so it is trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = [
    "LicenseStatus",
    "ADMISSIBLE_LICENSES",
    "SourceLicense",
    "UnlicensedSourceError",
    "normalize_license",
    "is_admissible",
    "check_admissible",
]


class LicenseStatus(str, Enum):
    """The license status a source corpus can carry.

    Only :attr:`PUBLIC_DOMAIN` and :attr:`LICENSED` are admissible for re-cook;
    every other value is refused (default-deny). ``UNKNOWN`` is the catch-all a
    missing / blank / unrecognised value normalises to — so an undeclared license
    can never be admitted by absence.
    """

    #: Public-domain — freely re-cookable (山海经, 封神演义, Shang–Zhou classics).
    PUBLIC_DOMAIN = "public_domain"
    #: Explicitly licensed for this use (an author-supplied, allowlisted license).
    LICENSED = "licensed"
    #: Declared unlicensed — REFUSED.
    UNLICENSED = "unlicensed"
    #: Declared copyrighted — REFUSED (a licensing liability for re-cook).
    COPYRIGHTED = "copyrighted"
    #: Declared use-restricted — REFUSED.
    RESTRICTED = "restricted"
    #: Missing / blank / unrecognised — REFUSED (default-deny catch-all).
    UNKNOWN = "unknown"


#: The conservative allowlist: ONLY these two statuses admit a source into the
#: re-cook corpus. Anything not in this frozenset is refused. Kept as data so the
#: policy is auditable in one place and cannot drift between the predicate and the
#: raising path.
ADMISSIBLE_LICENSES: frozenset[LicenseStatus] = frozenset(
    {LicenseStatus.PUBLIC_DOMAIN, LicenseStatus.LICENSED}
)


# ── normalisation: a raw DB/string value → a LicenseStatus (default-deny) ──────
# Maps the on-disk ``source_corpus.license`` text (and common synonyms) to the
# enum. ANYTHING not recognised — including None / '' / 'copyright' / 'cc-by-nc'
# / a typo — falls to UNKNOWN (refused). Public-domain accepts a couple of common
# spellings so the C2 default 'public-domain' (hyphen) round-trips to admissible.
_LICENSE_ALIASES: dict[str, LicenseStatus] = {
    "public_domain": LicenseStatus.PUBLIC_DOMAIN,
    "public-domain": LicenseStatus.PUBLIC_DOMAIN,
    "publicdomain": LicenseStatus.PUBLIC_DOMAIN,
    "pd": LicenseStatus.PUBLIC_DOMAIN,
    "cc0": LicenseStatus.PUBLIC_DOMAIN,
    "licensed": LicenseStatus.LICENSED,
    "license": LicenseStatus.LICENSED,
    "unlicensed": LicenseStatus.UNLICENSED,
    "copyrighted": LicenseStatus.COPYRIGHTED,
    "copyright": LicenseStatus.COPYRIGHTED,
    "restricted": LicenseStatus.RESTRICTED,
    "proprietary": LicenseStatus.RESTRICTED,
    "unknown": LicenseStatus.UNKNOWN,
}


class UnlicensedSourceError(PermissionError):
    """Raised when re-cook would consume a source that is not licensed / PD.

    A distinct, non-KeyError type (mirrors ``InactiveStrategyError``) so a caller
    can tell "this source is not admissible for re-cook" from a generic value
    error — and so a licensing refusal is impossible to mistake for an unrelated
    failure. PermissionError because, like the gate, it is an authorisation
    refusal: the source is not permitted into the re-cook corpus.
    """


@dataclass(frozen=True)
class SourceLicense:
    """The license metadata that travels with a re-cook source corpus.

    ``corpus_id`` / ``name`` identify the source (for the refusal message + the
    provenance record); ``status`` is the normalised :class:`LicenseStatus`. The
    strategy resolves one of these per source (from ``source_corpus.license``) and
    passes it through the licensing check at corpus-admission and at fact-emit.
    """

    corpus_id: str
    name: str
    status: LicenseStatus

    @classmethod
    def from_raw(cls, *, corpus_id: str, name: str, license: str | None) -> "SourceLicense":
        """Build from the raw ``source_corpus.license`` string (default-deny)."""
        return cls(corpus_id=corpus_id, name=name, status=normalize_license(license))

    @property
    def admissible(self) -> bool:
        return is_admissible(self.status)


def normalize_license(raw: str | None) -> LicenseStatus:
    """Coerce a raw license value to a :class:`LicenseStatus` (default-deny).

    ``None`` / empty / whitespace / an unrecognised token → :attr:`UNKNOWN`
    (refused). Recognised admissible spellings (``public-domain`` /
    ``public_domain`` / ``cc0`` / ``licensed``) map to their admissible status.
    Case- and surrounding-whitespace-insensitive.
    """
    if raw is None:
        return LicenseStatus.UNKNOWN
    key = raw.strip().lower()
    if not key:
        return LicenseStatus.UNKNOWN
    return _LICENSE_ALIASES.get(key, LicenseStatus.UNKNOWN)


def is_admissible(status: LicenseStatus) -> bool:
    """True iff ``status`` is in the conservative allowlist (PD or licensed)."""
    return status in ADMISSIBLE_LICENSES


def check_admissible(source: SourceLicense, *, stage: str) -> None:
    """Raise :class:`UnlicensedSourceError` unless ``source`` is admissible.

    ``stage`` (e.g. ``"corpus-admission"`` / ``"fact-emit"``) is folded into the
    error message so the refusal is traceable to WHERE the check fired (defence in
    depth — the same source is checked at both ends). A passing check returns None
    (the source may be re-cooked); a failing check raises and is never swallowed
    by the strategy (re-cook of that source is refused + escalated)."""
    if not is_admissible(source.status):
        raise UnlicensedSourceError(
            f"re-cook refused [{stage}]: source {source.name!r} "
            f"(corpus {source.corpus_id}) has license status "
            f"{source.status.value!r} — only public_domain / licensed sources may "
            f"be re-cooked (default-deny). A modern/news source needs an explicit "
            f"license before it can be re-contextualised into the 商周/封神 setting."
        )
