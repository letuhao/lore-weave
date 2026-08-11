"""Shadow comparison between two `GraphStore` adapters (plan T43, decision X1).

WHAT THIS IS FOR
----------------
X1: the engine is chosen by **measurement on real traffic**, not by argument. This wraps two
adapters, serves every call from the PRIMARY, and — best-effort — replays it against the
SECONDARY and records whether they agreed. The caller never sees the secondary: its result
is evidence, never an answer.

WHY IT COULD NOT EXIST UNTIL NOW
--------------------------------
`port-adoption-gate` measured the reason on 2026-08-12: the `GraphStore` port had **three
conforming adapters and ZERO call sites**. A shadow comparison of traffic that does not flow
through the port observes nothing, so the plan's coverage floor — *"no cutover while any port
operation has zero shadow observations"* — was not a slow number but an unreachable one.
T17's migration closed that: every port-covered operation now has zero DIRECT callers.

THE COVERAGE FLOOR IS THE POINT, AND IT IS ABOUT ABSENCE
--------------------------------------------------------
Merge/split/restore/coref/triage are rare. A comparison that ran for a week and reported
"100 % agreement" while never once exercising `restore_entity` would be evidence about
`relations_for` wearing the costume of evidence about the port. So `coverage_report()`
answers per OPERATION, and an operation at zero **blocks cutover** regardless of how well the
others agree.

⚠️ **DISAGREEMENT ≠ FAILURE, AND ABSENCE ≠ AGREEMENT.** Three outcomes are recorded, never
two: `agreed`, `diverged`, and `uncovered` (the secondary raised `NotImplementedError`).
`AgeGraphStore.status_at_order` / `events_in_window` deliberately raise
(`D-T42-AGE-EVENT-SURFACE`), and folding that into either of the other buckets would let a
COVERAGE gap read as a DATA result — the exact confusion those methods raise to prevent.

THE SECONDARY MUST NEVER BREAK THE CALLER
------------------------------------------
Every secondary call is wrapped. A shadow that can take production down converts a
measurement into an outage, and the first thing anyone would do is turn it off — which is how
the measurement never gets taken.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.ports.graph_store import EventAxis, GraphStore, RelationDirection

logger = logging.getLogger(__name__)

__all__ = ["ShadowGraphStore", "ShadowStats", "OPERATIONS"]

#: Every operation the port declares. The coverage report is keyed on THIS, not on what
#: happened to be called — an operation missing from the report would read as "no problem"
#: when it means "never observed", which is the failure this whole file guards.
OPERATIONS = (
    "resolve_or_merge_entity",
    "find_entities_by_name",
    "neighborhood",
    "archive_entity",
    "restore_entity",
    "upsert_relation",
    "relations_for",
    "status_at_order",
    "events_in_window",
)


@dataclass
class ShadowStats:
    """Per-operation observations. Three counters, deliberately — see the module docstring."""

    agreed: dict[str, int] = field(default_factory=dict)
    diverged: dict[str, int] = field(default_factory=dict)
    uncovered: dict[str, int] = field(default_factory=dict)
    errored: dict[str, int] = field(default_factory=dict)
    samples: list[tuple[str, str]] = field(default_factory=list)

    def observations(self, op: str) -> int:
        """Comparisons that actually produced a verdict.

        `uncovered` and `errored` are EXCLUDED: the secondary refused or blew up, so nothing
        was compared. Counting them would let a method that has never once been compared
        satisfy the coverage floor — which is precisely the lie the floor exists to catch.
        """
        return self.agreed.get(op, 0) + self.diverged.get(op, 0)


class ShadowGraphStore:
    """Serves from `primary`; compares against `secondary`. Satisfies `GraphStore`.

    Construct with two adapters that have both passed
    `tests/integration/db/test_graph_store_conformance.py`. That is not a formality: a
    comparison between two unproven implementations measures **agreement**, and two adapters
    can agree by sharing a bug. Conformance is what makes agreement mean correctness.
    """

    def __init__(self, primary: GraphStore, secondary: GraphStore) -> None:
        self._primary = primary
        self._secondary = secondary
        self.stats = ShadowStats()

    # ── the comparison ───────────────────────────────────────────────

    @staticmethod
    def _comparable(value: Any) -> Any:
        """Reduce a result to what the two engines must agree ON.

        Node ids are engine-assigned and must NOT be compared — Neo4j and AGE mint different
        ids for the same logical entity, so comparing them would report 100 % divergence and
        say nothing. What must agree is the identity tuple and the fields a caller acts on.
        """
        if value is None:
            return None
        if isinstance(value, list):
            return sorted(ShadowGraphStore._comparable(v) for v in value)
        for attrs in (
            ("canonical_name", "kind", "project_id", "archived_at"),   # Entity
            ("predicate", "confidence", "valid_from_ordinal"),          # Relation
        ):
            if all(hasattr(value, a) for a in attrs):
                return tuple(str(getattr(value, a)) for a in attrs)
        return str(value)

    async def _shadow(self, op: str, primary_result: Any, call) -> Any:
        try:
            secondary_result = await call(self._secondary)
        except NotImplementedError:
            # The adapter refused, on purpose. NOT a divergence and NOT an agreement.
            self.stats.uncovered[op] = self.stats.uncovered.get(op, 0) + 1
            return primary_result
        except Exception as exc:  # noqa: BLE001 — a shadow must never break the caller
            self.stats.errored[op] = self.stats.errored.get(op, 0) + 1
            logger.warning("shadow %s: secondary raised %s: %s", op, type(exc).__name__, exc)
            return primary_result

        a, b = self._comparable(primary_result), self._comparable(secondary_result)
        if a == b:
            self.stats.agreed[op] = self.stats.agreed.get(op, 0) + 1
        else:
            self.stats.diverged[op] = self.stats.diverged.get(op, 0) + 1
            if len(self.stats.samples) < 20:
                self.stats.samples.append((op, f"primary={a!r} secondary={b!r}"))
            logger.warning("shadow %s DIVERGED: primary=%r secondary=%r", op, a, b)
        return primary_result

    def coverage_report(self) -> dict:
        """Per-operation coverage, and whether a cutover is permitted.

        `blocked_by` lists every operation with zero real comparisons. An empty list is the
        only state in which the sealed design allows a cutover, and the report says so rather
        than leaving a reader to infer it from a table.
        """
        rows = {
            op: {
                "observations": self.stats.observations(op),
                "agreed": self.stats.agreed.get(op, 0),
                "diverged": self.stats.diverged.get(op, 0),
                "uncovered": self.stats.uncovered.get(op, 0),
                "errored": self.stats.errored.get(op, 0),
            }
            for op in OPERATIONS
        }
        blocked = [op for op in OPERATIONS if rows[op]["observations"] == 0]
        return {
            "operations": rows,
            "blocked_by": blocked,
            "cutover_permitted": not blocked
            and not any(r["diverged"] for r in rows.values()),
            "samples": list(self.stats.samples),
        }

    # ── the port surface ─────────────────────────────────────────────

    async def resolve_or_merge_entity(self, **kw):
        out = await self._primary.resolve_or_merge_entity(**kw)
        return await self._shadow("resolve_or_merge_entity", out,
                                  lambda s: s.resolve_or_merge_entity(**kw))

    async def find_entities_by_name(self, **kw):
        out = await self._primary.find_entities_by_name(**kw)
        return await self._shadow("find_entities_by_name", out,
                                  lambda s: s.find_entities_by_name(**kw))

    async def neighborhood(self, **kw):
        out = await self._primary.neighborhood(**kw)
        return await self._shadow("neighborhood", out, lambda s: s.neighborhood(**kw))

    async def archive_entity(self, **kw):
        out = await self._primary.archive_entity(**kw)
        return await self._shadow("archive_entity", out, lambda s: s.archive_entity(**kw))

    async def restore_entity(self, **kw):
        out = await self._primary.restore_entity(**kw)
        return await self._shadow("restore_entity", out, lambda s: s.restore_entity(**kw))

    async def upsert_relation(self, **kw):
        out = await self._primary.upsert_relation(**kw)
        return await self._shadow("upsert_relation", out, lambda s: s.upsert_relation(**kw))

    async def relations_for(self, **kw):
        out = await self._primary.relations_for(**kw)
        return await self._shadow("relations_for", out, lambda s: s.relations_for(**kw))

    async def status_at_order(self, **kw):
        out = await self._primary.status_at_order(**kw)
        return await self._shadow("status_at_order", out, lambda s: s.status_at_order(**kw))

    async def events_in_window(self, **kw):
        out = await self._primary.events_in_window(**kw)
        return await self._shadow("events_in_window", out, lambda s: s.events_in_window(**kw))
