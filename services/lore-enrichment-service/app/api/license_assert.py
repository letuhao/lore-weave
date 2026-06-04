"""Author-asserted license normalization (default-deny) for modes C + F.

The author asserts a license for pasted context (mode C) or an uploaded file
(mode F). Only ``public_domain | licensed | owned`` are admissible; ``owned`` is
stored as ``licensed`` (author-owned ⇒ re-cook-admissible, mirroring the /ground
handler). ``copyrighted`` — and anything unrecognised/blank — is REFUSED (the
caller turns the None into a 403): the platform never ingests material the user
can't ground a license claim on (spec §4). The hyphen spelling is accepted for
parity with ``strategies/licensing.py`` (the contract enum is underscore-only, so
the FE never sends it).
"""

from __future__ import annotations

_ASSERTED_LICENSE_MAP = {
    "public_domain": "public_domain",
    "public-domain": "public_domain",
    "licensed": "licensed",
    "owned": "licensed",
}


def resolve_asserted_license(raw: str | None) -> str | None:
    """Map a raw asserted license to the stored corpus license, or None if
    inadmissible (the caller raises 403). Case/whitespace-insensitive."""
    return _ASSERTED_LICENSE_MAP.get((raw or "").strip().lower())
