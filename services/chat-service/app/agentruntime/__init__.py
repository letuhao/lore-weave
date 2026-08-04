"""CP-1 · the membrane — a new declaration surface that starts empty and can reach nothing else.

Spec: ``docs/specs/2026-08-03-agent-runtime-unification/ARCHITECTURE.md`` §3 (membrane), §6.1 (M4).
Checkpoint: ``docs/plans/2026-08-04-agent-runtime-RUNSTATE.md`` → L1 · CP-1.

**The one sentence this package exists to make true:**

> Old declarations are not hidden. They are **absent**. There is no branch in the new assembler that
> can read the old catalog — not one that is disabled, not one behind a flag.

**Why the whole package imports only the standard library and itself.** Invisibility implemented as
a *filter* has been produced thirteen times in this repository, and every instance eventually leaked
or silently deleted the wrong thing. A filter is a code path from the old catalog to the new
surface; the only way to be sure a path does not leak is for it not to exist.
`scripts/agentruntime-membrane-gate.py` enforces that mechanically — an allowlist, not a denylist,
because a denylist is default-permitted and a new legacy module would join it uncovered.

**Two properties land here rather than in CP-0, on evidence.** P1 (*every narrowing registers*) and
P4 (*no column bound to a constant*) each failed **eleven consecutive verification rounds** as
retrofits onto the legacy runtime. The line separating what passed from what did not was never
difficulty or care — it was retrofit versus build. Here they are structural: one assembly point that
cannot drop without recording (`surface.py`), and one producer of an admitted declaration
(`admission.py`).
"""
from .admission import Admitted, admit, try_admit
from .contract import (
    CONTRACT_VERSION,
    ContractViolation,
    Declaration,
    Identity,
    derive_owning_service,
    identity_of,
)
from .manifest import (
    UnresolvedReference,
    UntrustedRow,
    build,
    declarations,
    generate,
    load,
    manifest_path,
    validate_document,
)
from .narrowing import Narrowing, NarrowingLog
from .surface import NarrowingRule, Surface, SurfaceAssembler, discover

__all__ = [
    "Admitted", "admit", "try_admit",
    "CONTRACT_VERSION", "ContractViolation", "Declaration", "Identity",
    "derive_owning_service", "identity_of",
    "UnresolvedReference", "UntrustedRow", "build", "declarations", "generate", "load",
    "manifest_path", "validate_document",
    "Narrowing", "NarrowingLog",
    "NarrowingRule", "Surface", "SurfaceAssembler", "discover",
]
