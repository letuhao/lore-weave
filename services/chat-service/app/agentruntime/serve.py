"""CP-2.7 · the ROUTE — what a turn served through the membrane advertises.

Spec: ``ARCHITECTURE.md`` §3 (M2/M3), §0.1, §7 (the control arm). Checkpoint: RUNSTATE → L2 · 2.7.

**This is the module that makes V-LIVE possible at all.** Every V-LIVE round in this effort — two
at CP-1, and every item at 2.1–2.5 — returned `CANNOT DETERMINE` for one mechanical reason: no
request path reached the package. `boot.py` gave it a production importer; this gives it a *turn*.

WHAT IT REPLACES, AND WHAT IT MUST NOT DISTURB
-----------------------------------------------
`stream_service._advertise_discovery_tools` is documented as **the single ADVERTISE chokepoint for
the discovery path**, with three callers. The route is a branch at that one function, so a turn on
the new arm advertises from the manifest and from nothing else.

🔴 **The legacy arm is CP-2's CONTROL GROUP (§7), so the flag is OFF by default and the branch is
`return` — not a merge, not a filter.** A control perturbed by changes nobody decided invalidates
the comparison before it starts (CP-1.9's argument, applied to the route itself). With the flag
off, `_advertise_discovery_tools` is byte-identical to what it was.

WHAT AN EMPTY MANIFEST ADVERTISES, AND WHY THAT IS THE POINT
-------------------------------------------------------------
`declarations: []` → **`[]`**. Not the core tools, not `find_tools`, not the frontend extras.
*Old declarations are not hidden. They are absent.* An arm that quietly kept the legacy core would
be the membrane leaking through its own route on day one — and it would make item **B** (*no legacy
declaration is reachable, by any route*) unmeasurable in exactly the place it most needs measuring.

That empty surface is what makes item **A** checkable: the agent must **say** it has no
declarations rather than answering as if none were needed. `statement_for` is the sentence, and it
is produced here rather than in the prompt assembly so that *what was advertised* and *what the
model was told about it* cannot drift apart.
"""
from __future__ import annotations

from typing import Any

from .assembly import offered_defs_for, withholding_notice
from .narrowing import NarrowingLog
from .surface import Surface, SurfaceAssembler

#: What the model is told when the manifest admits nothing at all.
#:
#: 🔴 **AN EMPTY SURFACE THE MODEL CANNOT DISTINGUISH FROM AN EMPTY WORLD PRODUCES CONFIDENT
#: FABRICATION** (§0.14.3). V-LIVE watched exactly that: the model announced a withheld tool *"does
#: not exist at all"*. The empty case is worse, because there is not even a search that would find
#: anything — so the statement has to be unambiguous about *which* emptiness this is.
NO_DECLARATIONS = (
    "No tools are available on this turn: this runtime has zero admitted declarations, which is a "
    "property of its configuration and not a judgement about your request. Say so plainly if the "
    "user asks for something a tool would do. Do not describe a tool call as performed."
)


def advertise(
    manifest_doc: dict,
    *,
    pass_number: int,
    log: NarrowingLog | None = None,
    pipeline: Any = (),
) -> tuple[list[dict], Surface]:
    """The tool definitions for one pass, and the `Surface` that accounts for them.

    Returns **both** on purpose. A caller that receives only the wire payload cannot record P1 —
    and *"the record is built somewhere else from something else"* is the eight-frame defect this
    package exists to make impossible. The `Surface` is the same object the conservation law
    already checked, so what is advertised and what is registered are one computation.
    """
    surface = SurfaceAssembler(manifest_doc, log=log).assemble(
        pass_number=pass_number, pipeline=pipeline)
    return payload_from_defs(offered_defs_for(manifest_doc, surface)), surface


def payload_from_defs(tool_defs) -> list[dict]:
    """Provider-shaped definitions — **offered only, and synchronously.**

    A deferred declaration is deliberately absent: that is what `defer_loading` means, and the
    library owns how a hidden tool later reaches the wire. Built from the definitions the caller
    already has rather than by awaiting `get_tools`, because reaching for `asyncio` inside a
    synchronous advertise chokepoint is how that chokepoint acquires a runtime dependency nobody
    asked for.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": d.name,
                "description": d.description or "",
                "parameters": dict(d.parameters_json_schema),
            },
        }
        for d in tool_defs
    ]


def statement_for(surface: Surface) -> str | None:
    """What the model must be TOLD about this surface, or `None` when there is nothing to say.

    Two different emptinesses, and collapsing them is the failure §0.14.3 names:

    * **nothing admitted** → `NO_DECLARATIONS`. There is no search that would find anything.
    * **something withheld** → the count, and that they are reachable (CP-2.4's notice).
    """
    if not surface.names and not surface.withheld:
        return NO_DECLARATIONS
    return withholding_notice(surface)


__all__ = [
    "NO_DECLARATIONS",
    "advertise",
    "payload_from_defs",
    "statement_for",
]
