"""The prose said someone died; the plan still needs them. Pure comparison, no LLM, no I/O.

THE DEFECT THIS CLOSES — and it is the acceptance test of the whole generation-SSOT run:
scene 1's prose kills Tô Thanh Dao, whom the plan has present in scene 2, and **a gate** must
catch it rather than a human reading the prose.

Why the existing canon guard cannot: `gone_cast_in_draft` asks the INVERSE question — *"is an
entity the graph already knows is gone being portrayed as present?"* The Mị Đế case has no such
entity. The death is being CREATED, right here, in a draft nothing has extracted yet, so the
knowledge snapshot has no row and the symbolic pre-filter finds no candidate at all. Measured
2026-08-01 on two isolated throwaway books: the scene that kills her and the scene that does
not BOTH came back `guard_status='checked'`.

THE SHAPE, and why it is split this way. The model is asked one thing it is reliably good at —
*fill a slot: who does this passage say died* (`status_effects`, an extractor that already
exists and is already prompt-taught) — and is never asked the thing it is unreliable at: whether
that contradicts the plan. That comparison is set intersection, and it lives here, in code, with
tests. Measured on the same two books with a local model at zero cost:

    CONTROL (tea house, 460w) → 2 events, kinds travel+dialogue, status_effects []
    DEATH   (gate, 407w)      → 1 event,  kind death, status_effects [('Tô Thanh Dao','gone')]

THE JOIN IS BY NAME, NOT BY ID. The extractor never sees an entity id — `entity_ref` is a
display string lifted from the prose. So this module takes a name index built from the cast's
`cached_name` + `cached_aliases` and reports anything it could not resolve as `unlinked` rather
than dropping it. An assertion the guard could not place is not a clean result; it is a gap,
and a caller that cannot see the gap will read silence as safety.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Iterable

__all__ = [
    "PLAN_CONFLICT_KIND",
    "norm_name",
    "asserted_gone",
    "name_index",
    "plan_conflicts",
]

#: The `CanonViolation.kind` this module produces. Distinct from `gone_entity_present` on
#: purpose: that one means "a known-dead character is acting", this one means "this passage is
#: what kills them, and the plan disagrees". They need different judge questions and they read
#: differently to an author, so collapsing them would lose the only useful distinction.
PLAN_CONFLICT_KIND = "plan_liveness_conflict"


def norm_name(s: str) -> str:
    """Comparison key for a display name.

    NFC first: the extractor's output and glossary's stored name both come from user text, and
    Vietnamese diacritics have two byte-identical-looking encodings. `Tô` composed and `Tô`
    decomposed are the same name and different strings — a join that skips this fails silently
    on exactly the language this project is written in.

    Deliberately NOT `exit_state.norm_key`: that one strips honorifics and rejects pronouns
    because it is minting an identity from prose. Here both sides are already identities, and
    stripping would make `Đại nhân Lạc` collide with `Lạc`.
    """
    return " ".join(unicodedata.normalize("NFC", (s or "")).split()).strip().casefold()


def asserted_gone(events: Iterable[Any]) -> dict[str, str]:
    """`{norm_name: display_name}` for every entity these events assert is GONE.

    Reads `status_effects` off whatever the extractor returned — objects or dicts, because the
    SDK hands back models and a persisted job hands back JSON, and one of those shapes always
    turns up later. Anything malformed is skipped rather than raising: this runs on a draft the
    author has already paid for.
    """
    out: dict[str, str] = {}
    for ev in events or ():
        effects = getattr(ev, "status_effects", None)
        if effects is None and isinstance(ev, dict):
            effects = ev.get("status_effects")
        for eff in effects or ():
            status = getattr(eff, "status", None)
            ref = getattr(eff, "entity_ref", None)
            if status is None and isinstance(eff, dict):
                status, ref = eff.get("status"), eff.get("entity_ref")
            if status != "gone" or not isinstance(ref, str):
                continue
            key = norm_name(ref)
            if key:
                out.setdefault(key, ref.strip())
    return out


def name_index(entities: Iterable[dict[str, Any]]) -> dict[str, str]:
    """`{norm_name: entity_id}` from glossary rows (`entity_id`, `cached_name`,
    `cached_aliases`).

    Aliases are indexed as well as the canonical name, because prose uses them: a scene that
    kills "Dao" must resolve to the entity stored as "Tô Thanh Dao". First writer wins per key,
    so a name shared by two entities resolves to whichever the caller listed first rather than
    flapping — an ambiguous name is a glossary problem, and silently picking a different entity
    per run would make the guard non-deterministic.
    """
    idx: dict[str, str] = {}
    for e in entities or ():
        eid = e.get("entity_id") if isinstance(e, dict) else None
        if not eid:
            continue
        for raw in [e.get("cached_name"), *(e.get("cached_aliases") or [])]:
            if isinstance(raw, str):
                key = norm_name(raw)
                if key:
                    idx.setdefault(key, str(eid))
    return idx


def plan_conflicts(
    gone: dict[str, str],
    names: dict[str, str],
    plan_status: dict[str, str] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """`(conflicts, unlinked)`.

    A conflict is an entity this passage asserts is GONE that the plan places in a LATER scene —
    i.e. `plan_status[entity_id] == "alive"`. The equality is explicit rather than "is present
    in plan_status": the plan rung only ever emits `alive` today, and a future rung that could
    say `gone` must not be read as agreement by an `in` test written before it existed.

    `unlinked` is every asserted-gone name no index entry matched. It is RETURNED, not logged
    and dropped: an assertion the guard could not place is a hole in coverage, and the caller
    decides whether that makes the check `checked` or a gap. Measured 2026-08-01: a live run
    where glossary held the cast with an EMPTY `cached_name` produced exactly this — the death
    was detected, the join found nothing, and a version of this function that returned only
    conflicts would have reported the scene clean.
    """
    plan = plan_status or {}
    conflicts: list[dict[str, Any]] = []
    unlinked: list[str] = []
    for key, shown in sorted(gone.items()):
        eid = names.get(key)
        if eid is None:
            unlinked.append(shown)
        elif plan.get(eid) == "alive":
            conflicts.append({"entity_id": eid, "name": shown})
    return conflicts, unlinked
