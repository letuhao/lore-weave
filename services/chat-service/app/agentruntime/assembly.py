"""CP-2.1 · P4 assembly on the bought toolset — **the deferring API, never the filtering one.**

Spec: ``docs/specs/2026-08-03-agent-runtime-unification/BUILD-VS-BUY.md`` §2 (P4 = **BUY**), §4.4
(*"P4 stops being ours to design"*); ``ARCHITECTURE.md`` §0.1, §3, §5.
Checkpoint: ``docs/plans/2026-08-04-agent-runtime-RUNSTATE.md`` → L2 · CP-2.1.

**This module is the first production import of `app.agentruntime`.** Every CP-1 V-LIVE round
returned `CANNOT DETERMINE` for one mechanical reason — nothing routed to the surface — so the
package had, literally, nothing observable about it. That is what this file changes, and it is the
only reason it exists before 2.2–2.10.

WHY THE API CHOICE IS THE WHOLE ITEM
-------------------------------------
`pydantic_ai.toolsets.AbstractToolset` offers two ways to reduce what a model is shown, declared
about fifty lines apart in ``abstract.py``:

============================  ==========================================  ==============
method                        what it does to a declaration               what it is
============================  ==========================================  ==============
``.filtered(fn)``             **removes** it from ``get_tools``           **a CEILING**
``.defer_loading(names)``     sets ``defer_loading=True`` — hidden from    **an ENABLER**
                              the wire *until discovered*, then revealed
============================  ==========================================  ==============

A filtered declaration is **gone**: not on the wire, not searchable, indistinguishable from one
that was never admitted. That is arm E's silent deletion with a library's name on it, and it makes
CP-2.4 (*withheld things stay reachable on request; the model can tell withheld from never
existed*) **unreachable by construction** — no later item can restore what the assembly deleted.

A deferred declaration is still in the toolset. `pydantic_ai` carries the authored `defer_loading`
flag for the whole run and tracks current visibility separately in
``ModelRequestParameters.revealed_tool_names``, so *hidden* and *absent* are different states in
the library's own model, not only in ours.

**So `.filtered(` is refused inside this package by `scripts/agentruntime-membrane-gate.py`, not by
this docstring.** The same argument as M2: a wrong result can be tested for, an absent code path
cannot — and this repository has produced "invisibility implemented as a filter" thirteen times.

WHAT THIS MODULE DOES NOT CLAIM
--------------------------------
* **It does not claim a declaration is well-described.** `ROW_FIELDS` has no `description` and no
  parameter schema today, so every tool def here is built with `description=None` and an empty
  object schema. Tool search scores on *name + description*, so a deferred declaration is
  discoverable **by name tokens only**. That is a real reduction in discoverability and it is
  recorded rather than papered over: the fields arrive with the first real declaration at CP-4,
  in the same change as their producer.
* **It does not make the package pure.** Admitting `pydantic_ai` to the membrane allowlist admits
  its transitive imports too, and the purity boundary (§1.8c) is static over *this package's own
  files*. The gate's scope entry keeps the coupling to one file; it cannot keep it to one library.
* **It does not route a turn.** Nothing calls this yet — that is CP-2.7's route, and until it
  exists a chat turn's V-LIVE verdict stays `CANNOT DETERMINE`.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Sequence

# 🔴 THE ONE EXTERNAL IMPORT IN THE PACKAGE, and it is admitted by an explicit scoped entry in
# `scripts/agentruntime-membrane-gate.py` — `ALLOWED_EXTERNAL["pydantic_ai"]`, restricted to this
# file by `ALLOWED_EXTERNAL_SCOPE`. `TOOL_SCHEMA_VALIDATOR` is taken from `pydantic_ai` rather than
# built here from `pydantic_core` deliberately: two allowlist roots would be twice the membrane
# hole for a validator the library already publishes.
from pydantic_ai.toolsets.abstract import AbstractToolset, ToolsetTool
from pydantic_ai.toolsets.external import TOOL_SCHEMA_VALIDATOR
from pydantic_ai.tools import ToolDefinition

from .surface import Surface, rows_of

#: The toolset id that appears in `ToolDefinition.toolset_id`. One value, because there is one
#: assembly point — the same argument that keeps `Surface` single-sited.
TOOLSET_ID = "agentruntime"

#: An admitted declaration carries no parameter schema today (see the docstring). An **empty
#: closed object** is the honest encoding of *"this declaration has not told us its arguments"* —
#: `{}` would mean *"anything goes"*, which is a claim the manifest has never made.
_NO_PARAMETERS: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}

#: What a caller must supply to execute a declaration. **Required, not defaulted.** A toolset that
#: could execute something it was not handed would be a code path from this package to whatever it
#: found — which is the one thing §3 forbids. The membrane holds because the executor arrives from
#: outside and the manifest arrives from disk, and neither can reach the other.
Executor = Callable[[str, dict[str, Any], Any], Awaitable[Any]]


class AssemblyMismatch(Exception):
    """A surface and a manifest that do not describe the same admitted set.

    Raised rather than reconciled. The two are supposed to be one fact seen twice — the assembler
    read `rows_of(manifest_doc)` and this module reads it again — so a disagreement means one of
    them is stale, and *choosing* between them here would silently pick a winner for a question
    nobody asked.
    """


class DeclarationToolset(AbstractToolset[Any]):
    """The admitted declarations, as a `pydantic_ai` toolset — **all of them, offered or not.**

    🔴 **`get_tools` returns the WITHHELD ones too, and that is the point of the class.** The
    obvious implementation returns `surface.names`; it is one line shorter and it deletes CP-2.4.
    What separates offered from withheld here is a **flag on the tool definition**
    (`defer_loading=True`, applied by `toolset_for`), never membership.

    The withheld ones additionally carry `metadata["excluded_by"]` — the `{tool, stage, reason,
    pass}` record the narrowing wrote. `pydantic_ai`'s metadata channel is documented as *"not sent
    to the model, but used for filtering and behaviour customisation"*, which is exactly the `_meta`
    channel `BUILD-VS-BUY.md` §2 identified: the reason reaches our own telemetry and never reaches
    the wire as prose the model has to interpret.
    """

    __slots__ = ("_defs", "_executor", "_id")

    def __init__(
        self,
        tool_defs: Sequence[ToolDefinition],
        *,
        executor: Executor,
        id: str = TOOLSET_ID,
    ) -> None:
        self._defs = tuple(tool_defs)
        self._executor = executor
        self._id = id

    @property
    def id(self) -> str | None:
        return self._id

    @property
    def tool_defs(self) -> tuple[ToolDefinition, ...]:
        return self._defs

    async def get_tools(self, ctx: Any) -> dict[str, ToolsetTool[Any]]:
        return {
            d.name: ToolsetTool(
                toolset=self,
                tool_def=d,
                # 🔴 ZERO, NOT A DEFAULT. A retried tool call is a second call the manifest never
                # authorised; whether a declaration is safe to re-run is C-13's question and it has
                # no answer in a row today. Silence would let the library pick one for us.
                max_retries=0,
                args_validator=TOOL_SCHEMA_VALIDATOR,
            )
            for d in self._defs
        }

    async def call_tool(
        self, name: str, tool_args: dict[str, Any], ctx: Any, tool: ToolsetTool[Any]
    ) -> Any:
        return await self._executor(name, tool_args, ctx)


def _tool_def(row: dict, *, excluded_by: dict | None) -> ToolDefinition:
    """One manifest row → one tool definition. **Nothing is invented here.**

    Every field either comes from the row or is the stated-absent encoding. In particular there is
    no generated description: a sentence assembled from `kind` and `owning_service` would read like
    a declaration's own words and would be this module's words, and the run has paid repeatedly for
    plausible-looking values nobody decided.
    """
    metadata: dict[str, Any] = {
        "kind": row["kind"],
        "owning_service": row["owning_service"],
        "lifecycle": row["lifecycle"],
        "contract_version": row["contract_version"],
        "admitted_against": row["admitted_against"],
    }
    if excluded_by is not None:
        metadata["excluded_by"] = excluded_by
    return ToolDefinition(
        name=row["id"],
        parameters_json_schema=_NO_PARAMETERS,
        description=None,
        metadata=metadata,
        toolset_id=TOOLSET_ID,
    )


def _defs_for(by_id: dict, offered, withheld_records) -> tuple[list, list]:
    """`(offered defs, withheld defs)` — **one construction, two consumers.**

    🔴 `toolset_for` wraps these for a `pydantic_ai` run; `serve.advertise` needs the offered ones
    on the wire, synchronously, at a chokepoint that has no business acquiring an event loop. Both
    read this. A second construction is how one rule acquires two behaviours the moment either is
    edited — measured twice in this run already (a duplicated gate walk, a claim corrected in one
    of three files).

    The deferral FLAG is not set here: that is `.defer_loading()`'s, and `serve` needs only the
    offered list, so nothing needs a private copy of the library's marking.
    """
    excluded_by = {w["tool"]: dict(w) for w in withheld_records}
    withheld_ids = [w["tool"] for w in withheld_records]
    return (
        [_tool_def(by_id[name], excluded_by=excluded_by.get(name)) for name in offered],
        [_tool_def(by_id[name], excluded_by=excluded_by[name]) for name in withheld_ids],
    )


def offered_defs_for(manifest_doc: dict, surface: Surface) -> list[ToolDefinition]:
    """The offered declarations' definitions, without building a toolset.

    Reconciliation is `toolset_for`'s and is not repeated: a caller that wants the wire payload
    **and** the guarantee that the surface matches the manifest asks for the toolset. This is the
    narrow accessor for a synchronous chokepoint, and it says so rather than implying more.
    """
    rows = rows_of(manifest_doc)
    by_id = {r["id"]: r for r in rows}
    return _defs_for(by_id, tuple(surface.names), tuple(surface.withheld))[0]


def toolset_for(
    manifest_doc: dict,
    surface: Surface,
    *,
    executor: Executor,
) -> AbstractToolset[Any]:
    """CP-2.1 — assemble one pass's surface onto the bought toolset.

    `manifest_doc` is read through `rows_of` for the second time (the assembler read it once), and
    the two readings are **reconciled rather than trusted**: the surface's offered set plus its
    withheld set must be exactly the manifest's admitted set, by identity *and* by cardinality.

    🔴 **The cardinality half is not redundant with the identity half.** A withheld record naming a
    declaration that is also offered satisfies the set union and is precisely the contradiction
    `pass_number` was added to catch — a verifier once found 19 of 303 withheld declarations
    simultaneously advertised on every pass. Sets cannot see it; counts can.

    Returns a toolset holding **every** admitted declaration, with the withheld ones marked for
    deferred loading. It never calls `.filtered()`, and the gate is what makes that a property
    rather than a promise.
    """
    rows = rows_of(manifest_doc)
    by_id = {r["id"]: r for r in rows}

    offered = tuple(surface.names)
    withheld_records = tuple(surface.withheld)
    withheld_ids = tuple(w["tool"] for w in withheld_records)

    if len(offered) + len(withheld_ids) != len(rows):
        raise AssemblyMismatch(
            f"the surface accounts for {len(offered)} offered + {len(withheld_ids)} withheld = "
            f"{len(offered) + len(withheld_ids)} declaration(s), and the manifest admits "
            f"{len(rows)}. A declaration that is both offered and withheld balances the SET and "
            f"not this count (§0.14.3)."
        )
    accounted = set(offered) | set(withheld_ids)
    if accounted != set(by_id):
        missing = sorted(set(by_id) - accounted)
        foreign = sorted(accounted - set(by_id))
        raise AssemblyMismatch(
            f"the surface and the manifest do not describe the same admitted set: "
            f"unaccounted-for in the manifest {missing}, named by the surface but not admitted "
            f"{foreign}. One of the two readings is stale, and this module does not pick a winner."
        )

    offered_defs, withheld_defs = _defs_for(by_id, offered, withheld_records)
    defs = offered_defs + withheld_defs

    toolset = DeclarationToolset(defs, executor=executor)
    # 🔴 THE ITEM, IN ONE CALL. `.defer_loading(...)` and `.filtered(...)` are both one method away
    # on this object and produce surfaces that are indistinguishable on the happy path — the
    # difference only shows up when the model asks for something it cannot see. `tool_names=()`
    # would mark nothing; `tool_names=None` would mark EVERYTHING, so the empty case is passed
    # explicitly rather than allowed to fall through to the library's default.
    return toolset.defer_loading(withheld_ids)


def advertised_names(tool_defs: Sequence[ToolDefinition]) -> tuple[str, ...]:
    """What a model would be shown on this pass — the tool defs that are **not** deferred.

    A helper for measurement, not for assembly: the whole point of `defer_loading` is that the
    library decides per-model how a hidden tool reaches the wire, so this answers the narrower
    question *"which of these did the assembly mark as visible"* and says nothing about bytes.
    """
    return tuple(d.name for d in tool_defs if not d.defer_loading)


def deferred_names(tool_defs: Sequence[ToolDefinition]) -> tuple[str, ...]:
    """The withheld-but-reachable set. CP-2.4's subject, available before CP-2.4 is built."""
    return tuple(d.name for d in tool_defs if d.defer_loading)


def withholding_notice(surface: Surface) -> str | None:
    """CP-2.4 · §0.14.3 — what the model must be TOLD, or `None` when there is nothing to tell.

    🔴 **THE ROW WAS HONEST AND THE SCREEN WAS NOT.** V-LIVE watched the model state that
    `book_list` *"does not exist at all"* while the same turn's row recorded it as withheld, with a
    stage and a reason. **An empty surface the model cannot distinguish from an empty world
    produces confident fabrication**, and no amount of correct telemetry prevents it — the record
    is read by us, afterwards.

    Reachability alone does not close this either. CP-2.1 made a withheld declaration discoverable
    and callable; a model that has concluded the tool does not exist **has no reason to search**.
    So the fact of withholding is stated, unprompted, on the turn it happens.

    **The COUNT, never the names.** Two reasons, and the first is the load-bearing one: listing the
    names puts back on the wire exactly what the narrowing removed, so a budget stage that cut five
    declarations would pay most of its own saving back and the narrowing would be theatre. The
    second is measured elsewhere in this effort — identifier confusion is the repository's largest
    failure class, and a bare list of names with no schemas is the shape that feeds it. The names
    are in the record, which is where a person reads them.

    `None` rather than *"0 withheld"*: a notice on every turn is noise the model learns to skip,
    and **absent and zero are different facts** — the same distinction §0.14.3 makes for `count`.
    """
    n = len(surface.withheld)
    if not n:
        return None
    return (
        f"{n} declaration{'s' if n != 1 else ''} that exist and are admitted were not offered on "
        f"this pass. They were withheld, not deleted, and they are reachable: search for the "
        f"operation you need before concluding that no tool provides it."
    )


def excluded_by(tool_defs: Sequence[ToolDefinition]) -> dict[str, dict]:
    """`{declaration id: the narrowing record that withheld it}` — the `_meta` reason channel."""
    out: dict[str, dict] = {}
    for d in tool_defs:
        record = (d.metadata or {}).get("excluded_by")
        if record is not None:
            out[d.name] = record
    return out


__all__ = [
    "AssemblyMismatch",
    "DeclarationToolset",
    "Executor",
    "TOOLSET_ID",
    "advertised_names",
    "deferred_names",
    "excluded_by",
    "toolset_for",
    "withholding_notice",
]
