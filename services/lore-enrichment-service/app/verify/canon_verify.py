"""Canon-verify — SHIM over `loreweave_grounding.verify` (mui #3 LE-migrate).

The three/four-check consistency verifier (contradiction / anachronism /
injection / regurgitation) was lifted into the shared `loreweave_grounding` SDK.
This module re-exports the SDK's public surface so every importer
(`from app.verify.canon_verify import CanonVerifier / FlagKind / Severity /
VerifyResult / VerifyFlag / CanonFact / CanonLookupFn / *_MARKERS`) resolves
unchanged — byte-identical behavior, single source of truth.

The one compatibility wrinkle: lore-enrichment's callers + tests construct
`CanonVerifier(read_port=…, canon_lookup=…, anachronism_markers=…)`. The SDK
verifier DROPPED `read_port` (FIX-1 had already made the graph-stats gate dead
code — `_read_stats` was uncalled). So the local `CanonVerifier` is a thin
subclass that still ACCEPTS `read_port` and ignores it, keeping every existing
call site working without edits. H0 unchanged: annotate-only, no write-back.
"""

from __future__ import annotations

from typing import Sequence

from loreweave_grounding.verify import (
    ANACHRONISM_MARKERS,
    FENGSHEN_ANACHRONISM_MARKERS,
    CanonFact,
    CanonLookupFn,
    FlagKind,
    Severity,
    VerifyFlag,
    VerifyResult,
)
from loreweave_grounding.verify import CanonVerifier as _SDKCanonVerifier

__all__ = [
    "FlagKind",
    "Severity",
    "VerifyFlag",
    "VerifyResult",
    "CanonFact",
    "CanonLookupFn",
    "CanonVerifier",
    "ANACHRONISM_MARKERS",
    "FENGSHEN_ANACHRONISM_MARKERS",
]


class CanonVerifier(_SDKCanonVerifier):
    """LE-migrate shim: the SDK `CanonVerifier` with the legacy `read_port=`
    constructor argument preserved (accepted + ignored). The graph-stats read it
    fed was already dead (FIX-1), so dropping it is behavior-preserving; keeping
    the kwarg keeps every existing caller + test unchanged."""

    def __init__(
        self,
        *,
        read_port: object | None = None,  # accepted for compat; unused (dead gate)
        canon_lookup: CanonLookupFn,
        anachronism_markers: Sequence[tuple[str, str]] = (),
    ) -> None:
        super().__init__(canon_lookup=canon_lookup, anachronism_markers=anachronism_markers)
