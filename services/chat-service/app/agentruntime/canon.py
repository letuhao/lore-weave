"""CP-1.8b · ONE canonical serialisation, and it is the only one this package may have.

`ARCHITECTURE.md` §0.14.2.

**Why one, and why now.** The repository currently carries **18 distinct canonical-JSON
implementations, 5 flag variants and 0 shared helpers**, with a precedent of digests being
*permanently baselined* because a serializer froze and the stored digests could no longer be
reproduced. This is the cheap moment for exactly one reason: **zero persisted digests exist yet**, so
the format can still be decided rather than excavated.

**Every rule below exists because getting it wrong is silent.** A canonicalisation defect does not
raise; it produces two digests for one value, or one digest for two values, and the consumer reads a
plausible number either way.

| rule | why |
|---|---|
| keys sorted, UTF-8, no insignificant whitespace | the ordinary requirements |
| **strings NFC-normalised before hashing** | the same grapheme must not hash two ways. This is U-1's decision applied to content-addressing — one Unicode form for the whole surface, decided once (§0.14.2) |
| **floats REFUSED, not formatted** | repr varies by platform and version, and a formatting choice made here would be invisible in the digest it changes. A caller that needs a number must decide its own representation, where the decision is visible |
| **a version prefix INSIDE the hashed bytes** | a future change to these rules then produces a *different digest* rather than a silent collision with the old format. Without it, a serializer change is indistinguishable from a content change — which is precisely how digests get baselined forever |
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any

#: Bumped when any rule above changes. It is hashed WITH the value, so a rule change is loud.
CANON_VERSION = "lw-canon/1"


class NotCanonicalisable(TypeError):
    """A value this serialisation refuses to represent, rather than represent badly."""


def nfc(value: str) -> str:
    """The Unicode form this package hashes in — **the one place that decides it.**

    🔴 **THIS DOCSTRING MADE A CLAIM A VERIFIER REFUTED BY EXECUTING IT, AND IT SURVIVED SEVEN
    ROUNDS SAYING IT.** It said `manifest.load` *"did not normalise, so an NFD spelling loaded and
    validated and produced **two `digest` values for one visibly identical document**"* — and the
    second half is false: `digest` normalises every string on the way in, so
    `digest(NFD) == digest(NFC)` and no drift gate can see a difference. The `canon.nfc(...)` call
    placed at that door on the strength of this sentence also normalised only the COPY fed to the
    check, leaving the row storing NFD either way; it was removed, and the sentence that justified it
    should have gone in the same change. **A rationale that outlives its own refutation is how the
    next reader re-adds the line.**

    What IS true, and is the whole of §0.14.2: exactly one place decides what the composed form is.
    That claim was false *inside this module* — `_norm` spelled `unicodedata.normalize("NFC", …)`
    three more times, which is the eighteen-implementations problem in miniature, in the file written
    to end it. `_norm` calls this now, so the module has one spelling and this function has callers.
    """
    return unicodedata.normalize("NFC", value) if isinstance(value, str) else value


def _norm(value: Any, *, path: str = "$") -> Any:
    """Recursively normalise for hashing. Raises rather than guessing."""
    # bool BEFORE int: `bool` is a subclass of `int`, so the int branch would swallow it and a
    # future `isinstance(v, int)` reader would see `True` as `1`.
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise NotCanonicalisable(
            f"{path}: float is not canonicalisable. Platform and version disagree on repr, and the "
            f"disagreement is invisible in the digest it changes. Represent it explicitly — a "
            f"string, or a scaled integer — where the choice is visible to a reader."
        )
    if isinstance(value, str):
        return nfc(value)
    if isinstance(value, dict):
        out = {}
        for k in value:
            if not isinstance(k, str):
                raise NotCanonicalisable(
                    f"{path}: keys must be strings; {type(k).__name__} has no stable ordering "
                    f"across runs, so the digest would depend on insertion order."
                )
            out[nfc(k)] = _norm(value[k], path=f"{path}.{k}")
        return out
    if isinstance(value, (list, tuple)):
        return [_norm(v, path=f"{path}[{i}]") for i, v in enumerate(value)]
    if isinstance(value, (set, frozenset)):
        raise NotCanonicalisable(
            f"{path}: a set has no order, so it has no canonical form. Sort it into a list at the "
            f"call site, where the ordering rule is a visible decision."
        )
    raise NotCanonicalisable(f"{path}: {type(value).__name__} has no canonical form")


def canonical_bytes(value: Any) -> bytes:
    """The exact bytes that get hashed. Exposed so a test can assert on them directly rather than
    only on a digest, in which every defect looks the same."""
    body = json.dumps(
        _norm(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return CANON_VERSION.encode("utf-8") + b"\x00" + body.encode("utf-8")


def digest(value: Any) -> str:
    """The content address of `value` — a hex sha256 over `canonical_bytes`."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
