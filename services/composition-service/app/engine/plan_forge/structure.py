"""D-PLANFORGE-BEATS-UNWIRED — resolve the ordered STORY BEATS a compile plans against.

## Why this module exists

`compile` emitted `package["beats"] = []` unconditionally. That is not a cosmetic gap — it silently
destroyed the entire structural layer of every plan:

1. `PassContext.beats` → `[]`
2. `map_beats_and_shape` → `beat_keys = set()`
3. `plan.parse_chapter_map` only accepts a `beat` the model returns **if it is in `beat_keys`**
   ⇒ **every** chapter's `beat_role` is forced to `None`, whatever the model said
4. `unmapped_beats` is filtered by the same empty set ⇒ always `[]`, so the blocking checkpoint
   reported perfect health while discarding 100% of its own output
5. `shape_tension_curve([None]*n)` collapses to ONE neutral run → a flat linear ramp

Live evidence (shipped 10-chapter arc, run `019f9d2e…`, artifact `019f9d2f-ff27…`): 10/10 chapters
`beat_role=NULL`, curve 50→72 straight line — no setup, no midpoint, no climax, no resolution.
Every chapter was drafted as narratively identical.

## Why the fix is a wire, not a build

Nothing here is new infrastructure. `structure_template` ships a table, 6 seeded built-ins, a repo,
CRUD routes and 5 MCP tools — and the beat rows are ALREADY in the exact shape the prompt wants
(`{key, label, order, purpose}`, with every key a member of `arc_plan._BANDS`). The LEGACY planner
wires them (`routers/plan.py` `/outline/decompose` REQUIRES a `structure_template_id` and passes
`tmpl.beats`). The V2 rewrite simply dropped the connection.

## The one rule this module must not break

**Never return a bare `[]` that reads as "this story has no structure".** An unresolvable structure
is ABSENT-WITH-A-NOTE (`source="unavailable"` + `note`), and the caller records it in the package so
the checkpoint can show it. That is the same absent≠zero law the pass adapters follow, and it is
precisely what was violated here: a silent `[]` looked like a successful compile for months.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol
from uuid import UUID

#: The built-in used when the author has not chosen a structure. NOT a hidden default: the resolved
#: choice and its `source` are recorded in `package["structure"]`, so the UI and the agent can both
#: see that it was defaulted and change it. 6 beats, and consecutive chapters may share a beat, so
#: it maps cleanly onto arcs of any length.
DEFAULT_BUILTIN_NAME = "Web Novel Arc"

StructureSource = Literal["run", "default", "unavailable"]


class _TemplatesRepo(Protocol):
    async def get(self, user_id: UUID, template_id: UUID) -> Any: ...
    async def list_for_user(self, user_id: UUID, *, include_archived: bool = False) -> list[Any]: ...


@dataclass(frozen=True)
class ResolvedStructure:
    """The beats a compile will plan against, plus WHERE they came from.

    `source` is the honesty field. A consumer that only reads `beats` cannot tell a deliberate
    author choice from a fallback from a total failure — and that indistinguishability is the bug
    this module was written to end.
    """

    beats: list[dict[str, Any]] = field(default_factory=list)
    template_id: UUID | None = None
    name: str = ""
    kind: str = ""
    source: StructureSource = "unavailable"
    note: str = ""

    @property
    def unshaped_beat_keys(self) -> list[str]:
        """Beat keys `shape_tension_curve` cannot band, so they fall to the neutral mid range.

        A custom structure whose keys the shaper does not know still assigns roles but produces a
        FLAT curve — a quieter version of the bug this module exists to fix. Surfacing the keys
        makes that visible instead of letting it look like a computed shape.
        """
        from app.engine.arc_plan import known_beat_keys

        known = known_beat_keys()
        return [str(b.get("key")) for b in self.beats if str(b.get("key")) not in known]

    def to_package(self) -> dict[str, Any]:
        """The `package["structure"]` provenance block. Always emitted — including on failure."""
        unshaped = self.unshaped_beat_keys
        return {
            "template_id": str(self.template_id) if self.template_id else None,
            "name": self.name,
            "kind": self.kind,
            "source": self.source,
            "beat_count": len(self.beats),
            "note": self.note,
            # Empty for every built-in. Non-empty ⇒ those chapters get a neutral tension target
            # however well the model assigns them, and the author should know their custom
            # structure is only half-understood.
            "unshaped_beat_keys": unshaped,
            "shapeable": not unshaped and bool(self.beats),
        }


def _beats_of(tmpl: Any) -> list[dict[str, Any]]:
    """The template's ordered beats, defensively normalised.

    Sorted by `order` when present: the L1 prompt renders them as "STRUCTURE BEATS (in order)" and
    asks the model to assign by position, so a shuffled list would quietly mis-shape the arc. Rows
    without a usable `key` are dropped — a keyless beat can never survive `parse_chapter_map`'s
    membership check, so carrying it would only inflate `unmapped_beats` with a beat no chapter
    could ever have been given.
    """
    raw = getattr(tmpl, "beats", None) or []
    rows = [b for b in raw if isinstance(b, dict) and str(b.get("key") or "").strip()]
    return sorted(rows, key=lambda b: b.get("order") if isinstance(b.get("order"), int) else 0)


async def resolve_structure(
    templates: _TemplatesRepo,
    user_id: UUID,
    *,
    structure_template_id: UUID | None,
) -> ResolvedStructure:
    """Resolve the run's story structure: explicit choice → named built-in default → absent.

    Degrade-safe at every step (a repo failure never breaks a compile), but never silent: each
    fallback carries the reason in `note`.
    """
    # ── 1 · the author's explicit choice ──────────────────────────────────────────────────────
    if structure_template_id is not None:
        try:
            tmpl = await templates.get(user_id, structure_template_id)
        except Exception:  # noqa: BLE001 — a degraded read falls back with a note, never a 500
            tmpl = None
        if tmpl is not None:
            beats = _beats_of(tmpl)
            if beats:
                return ResolvedStructure(
                    beats=beats, template_id=getattr(tmpl, "id", structure_template_id),
                    name=str(getattr(tmpl, "name", "")), kind=str(getattr(tmpl, "kind", "")),
                    source="run", note="",
                )
            # A chosen-but-EMPTY template is the author pointing at nothing. Falling through to the
            # default silently would override their choice; say what happened instead.
            fallback = await _default_structure(templates, user_id)
            return _with_note(
                fallback,
                f"the chosen structure '{getattr(tmpl, 'name', '')}' has no beats; "
                f"fell back to {fallback.name or 'no structure'}",
            )
        fallback = await _default_structure(templates, user_id)
        return _with_note(
            fallback,
            "the chosen structure was not found (deleted, archived, or another user's); "
            f"fell back to {fallback.name or 'no structure'}",
        )

    # ── 2 · no choice made → the recorded default ─────────────────────────────────────────────
    return await _default_structure(templates, user_id)


def _with_note(base: ResolvedStructure, note: str) -> ResolvedStructure:
    return ResolvedStructure(
        beats=base.beats, template_id=base.template_id, name=base.name, kind=base.kind,
        source=base.source, note=note,
    )


async def _default_structure(templates: _TemplatesRepo, user_id: UUID) -> ResolvedStructure:
    """The named built-in default, by NAME (built-in ids are seed constants, but a name lookup
    survives a re-seed and reads correctly in the provenance block)."""
    try:
        available = await templates.list_for_user(user_id)
    except Exception:  # noqa: BLE001
        return ResolvedStructure(
            note="the structure library could not be read; this plan has NO story structure "
                 "(every chapter's beat role will be empty)",
        )
    builtins = [t for t in available if getattr(t, "owner_user_id", None) is None]
    chosen = next((t for t in builtins if getattr(t, "name", "") == DEFAULT_BUILTIN_NAME), None)
    # A re-seed or a rename must not leave the compile structureless — any built-in with beats
    # beats no structure at all.
    if chosen is None:
        chosen = next((t for t in builtins if _beats_of(t)), None)
    if chosen is None:
        return ResolvedStructure(
            note="no built-in story structure is available (the library looks unseeded); this plan "
                 "has NO story structure (every chapter's beat role will be empty)",
        )
    return ResolvedStructure(
        beats=_beats_of(chosen), template_id=getattr(chosen, "id", None),
        name=str(getattr(chosen, "name", "")), kind=str(getattr(chosen, "kind", "")),
        source="default",
        note="no structure was chosen for this run; using the platform default — change it to "
             "reshape the arc",
    )
