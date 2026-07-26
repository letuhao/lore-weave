"""PROPOSE-BLIND (D-PLANFORGE-PROPOSE-BLIND) — the book-state gather lens.

`gather_existing_state(book_id, ...)` reads a SUMMARY-shaped, hard-capped view of what a book already
IS — its arcs, cast, manuscript spine, and in-play systems — so `propose` can CONTINUE the book
instead of re-inventing arcs/characters that already exist (the blind-propose defect this track fixes).

Design invariants (spec 2026-07-17-planforge-propose-existing-state §3):
- **Composes EXISTING reads, never re-derives** — arcs via `StructureRepo.list_tree`, cast via the KAL
  roster (`KalClient.roster`), spine via `OutlineRepo.recent_chapter_briefs`, systems from a
  caller-supplied latest package. No new cross-service client, table, or provider call.
- **Bounded by the Context Budget Law's allocator** — each item is a `packer.budget.Segment`; the
  shared `enforce_budget` drops lowest-priority items first (systems → arcs → cast → spine). The
  `chapter_count` scalar is the never-trimmed continuation anchor.
- **Absent ≠ zero (silent-success law)** — a missing/failed component is ABSENT-WITH-A-NOTE in
  `notes`, never a silent empty. A degraded read never raises; it degrades to empty + a note.
- **Cold-start is a no-op** — an empty book yields `is_empty()`, so `ground_on_existing` changes
  nothing for a fresh book (scenario-1 regression stays green).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.packer.budget import Segment, TokenCounter, default_counter, enforce_budget

# Drop-priority ladder (higher = kept longer), mirrors spec §3.2. Lower-value systems trim first.
_PRIO_SPINE = 90   # recent chapters — where the story IS, the plan continues from here
_PRIO_CAST = 80    # who already exists — the #1 re-invention risk
_PRIO_ARCS = 60    # committed structure
_PRIO_SYS = 40     # variables + motifs — softest, trimmed first

_ONE_LINE = 160    # per-item truncation for summaries/synopses


def _truncate(text: str, n: int = _ONE_LINE) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


#: A3 — kind_codes that mark a CHARACTER (a book-local slug, so a substring heuristic). Used to rank
#: character entities ahead of places/items in the roster, so the injected/listed cast is a person,
#: not a location. A kind that matches none of these is kept but ranked lower (never dropped).
_CHARACTER_KIND_HINTS = ("char", "person", "protagonist", "hero", "villain", "cast", "npc", "figure",
                         "nhân vật", "nhanvat")


def _is_character_kind(kind: str | None) -> bool:
    if not kind:
        return False
    k = kind.casefold()
    return any(h in k for h in _CHARACTER_KIND_HINTS)


@dataclass
class CastMember:
    """A character already in the book's glossary. `kind` (A3) is the entity's book-local kind_code
    when the gateway provides it (else None) — used to rank characters ahead of places/items."""
    name: str
    glossary_entity_id: str
    kind: str | None = None


@dataclass
class ArcSummary:
    title: str
    one_line: str


@dataclass
class ChapterBrief:
    story_order: int | None
    title: str
    synopsis: str


@dataclass
class ExistingStateBudget:
    """The token budget + per-component caps. `total` is owned by the Context Budget Law's
    plan-orientation allocation; the caps are pre-trim ceilings the PO can tune (spec §3.2)."""
    total: int = 1500
    recent_chapters_n: int = 12
    cast_cap: int = 40


@dataclass
class ExistingState:
    chapter_count: int                       # ABSOLUTE — never trimmed (the "how far along" anchor)
    recent_chapters: list[ChapterBrief]
    cast: list[CastMember]
    arcs: list[ArcSummary]
    variables: list[str]
    motifs: list[str]
    notes: dict[str, str] = field(default_factory=dict)
    grounded_fingerprint: str = ""

    def is_empty(self) -> bool:
        """Cold-start: nothing to ground on ⇒ the ground_on_existing flag is a no-op (scenario-1)."""
        return self.chapter_count == 0 and not self.cast and not self.arcs and not self.recent_chapters


# ── the seams this lens composes (structural typing so tests inject fakes) ──────────────────────────

class _StructureRepo(Protocol):
    async def list_tree(self, book_id: Any, *, include_archived: bool = False) -> list[Any]: ...


class _OutlineRepo(Protocol):
    async def recent_chapter_briefs(
        self, book_id: Any, *, limit: int = 12,
    ) -> tuple[int, list[dict[str, Any]]]: ...


class _KalClient(Protocol):
    async def roster(self, book_id: Any, *, user_id: Any = None, strict: bool = False) -> list[dict[str, Any]]: ...


def title_key(title: Any) -> str:
    """The dedup key for matching a proposed arc/entity against an existing one: `lower(strip(title))`.
    Promoted from `_rules_preflight`'s inline `_key` so the rules-path merge (below) and the pre-flight
    collision report share ONE definition — a drift between them would let the merge annotate an arc the
    preflight then flags as new (or vice versa)."""
    return str(title or "").strip().lower()


#: A1 — names that mean "the model produced no real character" (a placeholder to REPLACE with the
#: book's existing protagonist), case-folded. `normalize`/`_pad_traits_from_analyze` inject these.
_PLACEHOLDER_CAST_NAMES = frozenset({"", "nữ chính", "nu chinh", "[tbd]", "tbd", "char_main",
                                     "female protagonist", "protagonist", "main character"})


def merge_existing_into_spec(
    spec: dict[str, Any], existing: "ExistingState", *, inject_cast_max: int = 1,
) -> dict[str, Any]:
    """Merge-not-duplicate + DETERMINISTIC CAST INJECTION (spec §3.4 + A1): reconcile a proposed spec
    IN PLACE against the book's existing state, no LLM. Two passes:

    1. ANNOTATE (both paths): a proposed arc whose title matches an existing arc gets
       `continues_existing: true`; a proposed character whose name matches an existing glossary cast
       member carries that member's `glossary_entity_id` (so roster-bind resolves to the SAME entity)
       + `continues_existing: true`.
    2. INJECT (A1): when the model emitted only a PLACEHOLDER protagonist (`Nữ chính`/`[TBD]`/empty —
       the A/B eval proved prompt grounding does not make the model reuse existing names), REPLACE that
       placeholder with the book's existing protagonist (name + entity id), deterministically. Capped
       by `inject_cast_max` (default 1 = protagonist only; 0 disables). A genuinely NEW named character
       is the author's choice and is NEVER overridden. Cold-start / empty existing ⇒ no-op.
    """
    if existing.is_empty():
        return spec
    existing_arc_keys = {title_key(a.title) for a in existing.arcs}
    for arc in spec.get("arcs", []) or []:
        if isinstance(arc, dict):
            arc["continues_existing"] = title_key(arc.get("title", "")) in existing_arc_keys
    existing_names = {c.name.casefold() for c in existing.cast if c.name}
    cast_by_name = {c.name.casefold(): c.glossary_entity_id for c in existing.cast if c.name}
    for char in (spec.get("layers", {}) or {}).get("characters", []) or []:
        if not isinstance(char, dict):
            continue
        eid = cast_by_name.get(str(char.get("name") or "").casefold())
        if eid:
            char["glossary_entity_id"] = eid
            char["continues_existing"] = True

    # ── A1 injection ──
    if inject_cast_max > 0 and existing.cast:
        chars = (spec.get("layers", {}) or {}).get("characters")
        if isinstance(chars, list):
            proto = next(
                (c for c in chars if isinstance(c, dict) and (c.get("role") or "").strip().lower() == "protagonist"),
                None,
            )
            if proto is None and chars and isinstance(chars[0], dict):
                proto = chars[0]
            if proto is not None:
                name = str(proto.get("name") or "").strip().casefold()
                # inject ONLY over a placeholder — never over a name the model chose, and never when
                # the model already used an existing name (the annotate pass handled that).
                if name in _PLACEHOLDER_CAST_NAMES and name not in existing_names:
                    injected = existing.cast[0]  # A3: cast is character-kind-ranked, so [0] is a person
                    proto["name"] = injected.name
                    proto["glossary_entity_id"] = injected.glossary_entity_id
                    proto["continues_existing"] = True
                    proto.setdefault("role", "protagonist")
    return spec


def render_existing_state_prompt(state: "ExistingState") -> str:
    """Render the EXISTING STATE section injected into the LLM propose prompts (analyze + materialize).
    Empty string on a cold-start/empty state, so the prompt is byte-identical to the blind path when
    there is nothing to ground on. The CONTINUITY rule in the system prompts references this section."""
    if state.is_empty():
        return ""
    lines: list[str] = [
        "EXISTING STATE — this book already exists. CONTINUE it; do NOT re-invent what is listed here.",
        f"- Chapters written: {state.chapter_count}"
        + (f" ({state.notes.get('spine', '')})" if state.notes.get("spine") else ""),
    ]
    if state.recent_chapters:
        lines.append("- Recent chapters (the plan must continue from here):")
        for cb in state.recent_chapters:
            lines.append(f"  - {cb.title}: {cb.synopsis}".rstrip(": "))
    if state.cast:
        names = ", ".join(c.name for c in state.cast)
        lines.append(f"- Existing cast (REFERENCE by these exact names; do not rename or re-invent): {names}")
    if state.arcs:
        titles = ", ".join(a.title for a in state.arcs)
        lines.append(f"- Existing arcs (continue these; do not duplicate a title): {titles}")
    if state.variables or state.motifs:
        sys_bits = []
        if state.variables:
            sys_bits.append("variables: " + ", ".join(state.variables))
        if state.motifs:
            sys_bits.append("motifs: " + ", ".join(state.motifs))
        lines.append("- Systems already in play: " + " | ".join(sys_bits))
    return "\n".join(lines)


def _extract_systems(latest_package: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    """Best-effort read of the variables/motifs already in play, from a caller-supplied latest
    compiled package (the caller has the run context; the lens stays pure). Empty when absent."""
    if not isinstance(latest_package, dict):
        return [], []
    variables: list[str] = []
    layers = latest_package.get("layers")
    if isinstance(layers, dict):
        for v in layers.get("variables", []) or []:
            if isinstance(v, dict):
                label = v.get("code") or v.get("name")
                if label:
                    variables.append(str(label))
    motifs: list[str] = []
    for m in latest_package.get("motifs", []) or []:
        if isinstance(m, dict):
            label = m.get("label") or m.get("name") or m.get("title")
            if label:
                motifs.append(str(label))
        elif isinstance(m, str):
            motifs.append(m)
    return variables, motifs


def _fingerprint(chapter_count: int, arcs: list[ArcSummary], cast: list[CastMember]) -> str:
    """Deterministic — a re-propose over the SAME book state yields the same fingerprint (so a
    re-propose is reproducible and the freshness model can compare it). Sorted, so read order can't
    perturb it."""
    payload = "|".join([
        f"n={chapter_count}",
        "arcs=" + ",".join(sorted(a.title.strip().lower() for a in arcs)),
        "cast=" + ",".join(sorted(c.glossary_entity_id for c in cast)),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def gather_existing_state(
    book_id: Any,
    *,
    structure_repo: _StructureRepo,
    outline_repo: _OutlineRepo,
    kal_client: _KalClient,
    user_id: Any = None,
    latest_package: dict[str, Any] | None = None,
    budget: ExistingStateBudget | None = None,
    counter: TokenCounter | None = None,
) -> ExistingState:
    budget = budget or ExistingStateBudget()
    counter = counter or default_counter()
    notes: dict[str, str] = {}

    # ── arcs (StructureRepo.list_tree — the same read _rules_preflight uses) ──
    try:
        tree = await structure_repo.list_tree(book_id)
        arcs = [
            ArcSummary(title=(n.title or ""), one_line=_truncate(n.summary or ""))
            for n in tree if getattr(n, "kind", None) == "arc"
        ]
        notes["arcs"] = f"{len(arcs)} existing arc(s)" if arcs else "no existing arcs"
    except Exception:  # noqa: BLE001 — a degraded read is absent-with-a-note, never a raise
        arcs, notes["arcs"] = [], "arc read failed — omitted"

    # ── cast (KAL roster — drained, degrade-tolerant; name + entity id only) ──
    try:
        roster = await kal_client.roster(book_id, user_id=user_id)
        full = len(roster)
        all_cast = [
            CastMember(name=str(e["name"]), glossary_entity_id=str(e["entity_id"]), kind=e.get("kind"))
            for e in roster
            if e.get("name") and e.get("entity_id")
        ]
        # A3 — rank CHARACTER-kind entities first (stable) so the cap keeps people, not places, and the
        # injected/listed protagonist is a character. When no kinds are present (older gateway) this is
        # a stable no-op (all rank equal → original order preserved).
        ranked = sorted(all_cast, key=lambda c: 0 if _is_character_kind(c.kind) else 1)
        cast = ranked[: budget.cast_cap]
        n_char = sum(1 for c in cast if _is_character_kind(c.kind))
        rank_note = f", {n_char} character-kind first" if any(c.kind for c in all_cast) else ""
        notes["cast"] = (
            f"showing {len(cast)} of {full} cast member(s){rank_note}" if full > len(cast)
            else (f"{full} cast member(s){rank_note}" if full else "no glossary characters yet")
        )
    except Exception:  # noqa: BLE001
        cast, notes["cast"] = [], "cast read failed — omitted"

    # ── manuscript spine (OutlineRepo.recent_chapter_briefs) ──
    try:
        chapter_count, briefs = await outline_repo.recent_chapter_briefs(
            book_id, limit=budget.recent_chapters_n,
        )
        recent = [
            ChapterBrief(story_order=b.get("story_order"), title=b.get("title") or "",
                        synopsis=_truncate(b.get("synopsis") or ""))
            for b in briefs
        ]
        notes["spine"] = (
            f"{chapter_count} chapter(s), showing last {len(recent)}" if chapter_count
            else "no outline chapters yet"
        )
    except Exception:  # noqa: BLE001
        chapter_count, recent, notes["spine"] = 0, [], "spine read failed — omitted"

    # ── in-play systems (best-effort from the caller-supplied latest package) ──
    variables, motifs = _extract_systems(latest_package)
    notes["systems"] = (
        f"{len(variables)} variable(s), {len(motifs)} motif(s) in play"
        if (variables or motifs) else "no compiled systems yet"
    )

    # ── budget trim: each item is a Segment; enforce_budget drops lowest-priority first ──
    segments: list[Segment] = []
    refs: list[tuple[str, Any]] = []

    def _add(component: str, item: Any, text: str, priority: int) -> None:
        seg = Segment(block=component, text=text, priority=priority)
        segments.append(seg)
        refs.append((component, item))

    for cb in recent:
        _add("spine", cb, f"{cb.title} — {cb.synopsis}", _PRIO_SPINE)
    for cm in cast:
        _add("cast", cm, cm.name, _PRIO_CAST)
    for a in arcs:
        _add("arcs", a, f"{a.title} — {a.one_line}", _PRIO_ARCS)
    for v in variables:
        _add("var", v, v, _PRIO_SYS)
    for m in motifs:
        _add("motif", m, m, _PRIO_SYS)

    if segments:
        result = enforce_budget(segments, budget.total, counter)
        kept = {id(s) for s in result.kept}
        keep = {comp: [] for comp in ("spine", "cast", "arcs", "var", "motif")}
        for (comp, item), seg in zip(refs, segments):
            if id(seg) in kept:
                keep[comp].append(item)
        # reconstruct trimmed lists + note any drops (never a silent truncation)
        for comp, target_before in (("spine", recent), ("cast", cast), ("arcs", arcs)):
            dropped = len(target_before) - len(keep[comp])
            if dropped > 0:
                notes[{"spine": "spine", "cast": "cast", "arcs": "arcs"}[comp]] += \
                    f" ({dropped} trimmed for budget)"
        recent, cast, arcs = keep["spine"], keep["cast"], keep["arcs"]
        variables, motifs = keep["var"], keep["motif"]

    return ExistingState(
        chapter_count=chapter_count,
        recent_chapters=recent,
        cast=cast,
        arcs=arcs,
        variables=variables,
        motifs=motifs,
        notes=notes,
        grounded_fingerprint=_fingerprint(chapter_count, arcs, cast),
    )
