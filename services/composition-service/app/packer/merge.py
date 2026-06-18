"""C25 — two-project base+delta merge + entity-override mutation (dị bản M0).

A DERIVATIVE Work grounds on TWO knowledge partitions (G2): the inherited BASE
(the source Work's project, read `≤ branch_point`) and the DELTA (the derivative's
own project, read full). This module is the pure-function seam that:

  • applies `entity_override[]` to the inherited base entities BEFORE they reach
    the prompt window (`apply_entity_overrides`) — entity-field overrides
    (name/summary) + an added canon-rule scope. The caller re-reads + re-applies
    the override set on EVERY pack (self-syncing — there is NO cache here);
  • merges base+delta `present` / `timeline` / `lore` with DELTA PRECEDENCE on
    collision (`merge_present` / `merge_timeline` / `merge_lore`).

NORMALIZATION SEAM (recurring cross-service bug class): base vs delta entity
identity is reconciled AFTER normalizing the two partitions' name/anchor — a
present item is keyed by its stable glossary anchor (`entity_id`) when present,
else by a case/whitespace-folded name. An override's `target_entity_id` is matched
against that same reconciled key, so a normalization mismatch can't silently drop
an override or duplicate an entity.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

# Extra canon rules contributed by entity overrides surface as derivative canon
# (the M0 "added canon rule" override scope). Carries the rule text so the packer
# can render it in the <canon> block alongside the inherited rules.
OVERRIDE_CANON_FIELD = "canon_rule"


def _norm_name(name: Any) -> str:
    """Case/whitespace-folded entity name — the fallback identity when no stable
    glossary anchor id is available on a present item."""
    return " ".join(str(name or "").split()).casefold()


def _present_key(item: dict[str, Any]) -> str:
    """Reconciled identity for a `present` item: the stable glossary anchor
    (`entity_id`) when set, else the normalized name. This is the SAME key an
    override's `target_entity_id` is matched against (see `apply_entity_overrides`)
    so the base/delta partitions and the override set all reconcile on one axis."""
    eid = item.get("entity_id")
    if eid:
        return f"id:{eid}"
    return f"name:{_norm_name(item.get('name'))}"


def merge_present(
    base: list[dict[str, Any]], delta: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Union base + delta present-entity lists with DELTA PRECEDENCE on collision
    (reconciled by `_present_key`). Delta order is preserved; base-only entities
    append after, so the derivative's view leads."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in delta:
        k = _present_key(item)
        if k in seen:
            continue
        seen.add(k)
        out.append(item)
    for item in base:
        k = _present_key(item)
        if k in seen:
            continue  # delta already provided this entity → delta wins
        seen.add(k)
        out.append(item)
    return out


def _event_key(e: dict[str, Any]) -> str:
    return f"{_norm_name(e.get('title'))}|{e.get('event_order')}"


def merge_timeline(
    base: list[dict[str, Any]], delta: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Union base + delta timeline events, DELTA wins on a (title, event_order)
    collision. Order is delta-first then base-fill (the packer's downstream spoiler
    re-filter + budget ladder re-sort by priority, so insertion order is not the
    in-world axis)."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for e in delta:
        k = _event_key(e)
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    for e in base:
        k = _event_key(e)
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out


def _lore_key(h: dict[str, Any]) -> str:
    # Lore hits dedup on source passage id (+ a text fallback so two ingest copies
    # of the same passage with no source_id still fold).
    return f"src:{h.get('source_id')}" if h.get("source_id") else f"txt:{_norm_name(h.get('text'))}"


def merge_lore(
    base: list[dict[str, Any]], delta: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Union base + delta lore hits, DELTA wins on a same-passage collision."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for h in delta:
        k = _lore_key(h)
        if k in seen:
            continue
        seen.add(k)
        out.append(h)
    for h in base:
        k = _lore_key(h)
        if k in seen:
            continue
        seen.add(k)
        out.append(h)
    return out


def apply_entity_overrides(
    present: list[dict[str, Any]], overrides: list[Any] | None,
    *, target_anchor: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Mutate INHERITED present entities per `entity_override[]` (M0 scope: entity
    FIELDS = name/summary + an added canon-rule). Matches each override's
    `target_entity_id` against the present item's reconciled identity (anchor id).
    Returns (mutated_present, extra_canon_rules).

    CROSS-SPACE RECONCILIATION (normalization seam): a present item is keyed by its
    GLOSSARY anchor (`entity_id`), but an override's `target_entity_id` may be a
    KNOWLEDGE canonical_id (the C24 wizard records the knowledge node id). The
    caller resolves that knowledge id → its glossary anchor and passes the mapping
    in `target_anchor` ({raw_target: glossary_anchor}); we match an override against
    BOTH its raw target AND its resolved anchor, so a knowledge-id-vs-glossary-id
    drift can't silently drop the override.

    SELF-SYNCING: this is a pure re-application over the CURRENT override list — the
    caller passes a freshly-read `overrides` on every pack, so an edited override
    takes effect next pack with NO cache. A non-matching override contributes
    nothing (no accidental mutation of a different entity)."""
    if not overrides:
        return present, []

    anchor_map = target_anchor or {}
    # INVARIANT (adversary review): every `present` item carries a stable glossary
    # `entity_id` (gather_present skips anchorless bios; the relations path falls back
    # to `glossary_entity_id or key`), so `_present_key` is always `id:<…>` here and
    # matching overrides by id reaches every present entity. If a future lens ever
    # emits an anchorless present item (key `name:<…>`), an id-targeted override would
    # silently miss it — add a name-form fallback to `by_id` at that point.
    # Index overrides by the reconciled present-key (`id:<glossary_anchor>`) so the
    # match axis is identical to the base/delta merge axis. An override is indexed
    # under its raw target AND (if resolvable) its glossary anchor.
    by_id: dict[str, Any] = {}
    for ov in overrides:
        tid = getattr(ov, "target_entity_id", None)
        if tid is None:
            continue
        by_id[f"id:{tid}"] = ov
        resolved = anchor_map.get(str(tid))
        if resolved:
            by_id[f"id:{resolved}"] = ov

    extra_canon: list[str] = []
    mutated: list[dict[str, Any]] = []
    for item in present:
        key = _present_key(item)
        ov = by_id.get(key)
        if ov is None:
            mutated.append(item)
            continue
        fields = getattr(ov, "overridden_fields", None) or {}
        new_item = dict(item)
        if "name" in fields and fields["name"]:
            new_item["name"] = str(fields["name"])
        # The present-item bio field is `summary` (mapped from glossary
        # short_description). The override JSON may carry it as `summary` OR
        # `description` (the C24 wizard authors `description`) — reconcile both to
        # the one present field so a field-NAME drift doesn't silently drop the
        # override (the cross-service normalization seam). `summary` wins if both.
        if "description" in fields:
            new_item["summary"] = str(fields["description"])
        if "summary" in fields:
            new_item["summary"] = str(fields["summary"])
        rule = fields.get(OVERRIDE_CANON_FIELD)
        if rule:
            extra_canon.append(str(rule))
        mutated.append(new_item)

    return mutated, extra_canon


def _coerce_uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None
