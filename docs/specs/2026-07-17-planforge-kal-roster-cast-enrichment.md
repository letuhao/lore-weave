# PlanForge — KAL roster cast enrichment (A3)

> **Status:** build-ready spec (design) — **NOT built, deliberately deferred** (2026-07-17). The track
> goal was met by A1+A2 without it (grounding beats blind, ceiling flipped; A1 uses `cast[0]` which
> works). A3 is a cross-service quality refinement (knowledge-gateway TS + likely glossary Go for the
> upstream `kind` field) that upgrades protagonist SELECTION (kind-ranked vs first-drained) — genuinely
> off the critical path. Build it when the knowledge-gateway track opens, or fold the tiny TS
> passthrough in then. Part of the PlanForge-v2 Proposer-Grounding track.

## 1 · The problem
The PROPOSE-BLIND gather lens can only present existing cast as `{name}` — no role, no kind, no
importance rank — because the KAL roster is DELIBERATELY projection-restricted:
- `services/knowledge-gateway/src/kal/kal-read.controller.ts:106-127` — the `roster` route proxies
  `glossary /internal/books/{id}/entities` and maps each item to **only** `{entity_id, name}`
  (comment: *"Projection-restricted (id+name)"*).
- The composition-side `KalClient.roster()` (`clients/kal_client.py`) faithfully returns that shape.

Consequences for grounding: the gather lens caps cast **by arrival order, not importance** (a 500-cast
book keeps an arbitrary 40), and the EXISTING STATE block can only list bare names — the proposer can't
be told "Diệp Vấn Vũ is the protagonist" vs a walk-on. The A1 protagonist injection currently guesses
`existing.cast[0]`; a `kind`/mention-rank would make it PICK the real protagonist.

## 2 · The fix — widen the roster projection (carefully)
Add `kind` (and, if cheap upstream, a mention/importance signal) to the roster projection, so the gather
lens can rank + label cast.

### 2.1 knowledge-gateway (TS) — the projection
`kal-read.controller.ts` roster mapping:
```ts
const items = ((data?.items ?? []) as Array<Record<string, unknown>>).map((e) => ({
  entity_id: e.entity_id,
  name: e.name ?? e.cached_name,
  kind: e.kind ?? e.entity_kind ?? null,      // NEW — passthrough IF upstream provides it
}));
```
Only widen what the upstream `glossary /internal/books/{id}/entities` ALREADY returns — do not add a new
upstream query. **First verify** the glossary entities endpoint includes `kind`/`entity_kind` in its
item projection; if it doesn't, that upstream widening (glossary-service, Go) is a prerequisite sub-task,
scoped separately.

### 2.2 Why it was restricted — respect the reason
The projection is deliberate (bounded payload for a keyset-drained, complete-in-aggregate list). Adding
ONE short scalar (`kind`) is low-cost; do NOT add heavy fields (descriptions, relations). Keep the drain
bounded. If a mention/importance rank isn't a cheap column upstream, DEFER it — `kind` alone already lets
A1 pick the protagonist.

### 2.3 composition consumers
- `KalClient.roster()` — pass `kind` through on each item (still degrade-safe; `kind` optional).
- `existing_state.CastMember` — add `kind: str | None`; the gather lens ranks/labels: protagonist-kind
  first, then by kind priority, capping by IMPORTANCE not arrival order. The EXISTING STATE prompt block
  labels cast ("protagonist: X; supporting: Y, Z").
- A1's injection picks the protagonist-kind member instead of `cast[0]`.

## 3 · Acceptance criteria
1. `KalClient.roster()` returns `kind` per item when the glossary provides it; absent ⇒ `None`
   (degrade-safe, no regression to the id+name callers).
2. The gather lens caps a 500-cast book by importance (protagonist/major kinds kept), not arrival order,
   and `notes["cast"]` says how it ranked.
3. A1 injection selects the protagonist-kind existing member (not `cast[0]`).
4. No payload blow-up: the roster item gains ONE short scalar; the drain stays bounded.

## 4 · Test
- knowledge-gateway: a controller test that the roster item carries `kind` when upstream returns it.
- composition: `KalClient.roster` maps `kind`; the gather lens ranks by kind (unit with a mixed roster).
- Live smoke: a book with a labelled protagonist → the EXISTING STATE block labels it.

## 5 · Risk / size
M · cross-service (knowledge-gateway TS + possibly glossary-service Go for the upstream field). Not on
the A1→B critical path — names alone let A1 anchor a protagonist; A3 upgrades the RANK/label quality.
Sequence it when the knowledge-gateway track is open, or fold the tiny TS passthrough into that track.

## 6 · Standards note
Stays within the KAL boundary (INV-KAL) — composition reads cast ONLY through `KalClient`/the gateway,
never the glossary `/internal` route directly. This spec widens the gateway's projection, it does not
add a new direct read path.
