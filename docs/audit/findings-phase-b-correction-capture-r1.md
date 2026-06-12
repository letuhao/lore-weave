# Adversary review — Phase B correction capture (round 1)

**Verdict: REJECTED** (2 BLOCK + 1 WARN). The idempotency/dedup key the entire
correction spine is built on does not exist on the wire as designed, and a
secondary identity bug in the relation predicate_fix path can corrupt the live
graph.

---

## F1 — BLOCK — `origin_event_id` (the dedup key) is never put on the Redis Stream

**Design claim.** spec lines 127/130/140: `origin_event_id` = "outbox row id
(uuidv7) — dedup key on redelivery"; dedup via
`UNIQUE (origin_service, origin_event_id)` + `ON CONFLICT DO NOTHING`. Line 45
asserts the relay "keys the Redis stream off the `aggregate_type` column … solid."

**Evidence (relay does NOT carry the row id).**
`services/worker-infra/internal/tasks/outbox_relay.go:124-165`: the outbox row
`id` IS selected (line 126) and stringified (line 149) but the `XAdd` Values map
(lines 159-164) contains only `event_type`, `aggregate_id`, `payload`, `source`
— **`id` is never added to the stream message.** It is used only for `event_log`
(line 177) and the `published_at` UPDATE (line 180). Consumer side confirms:
`knowledge-service/app/events/consumer.py:238-260` (`_parse_event`) +
`dispatcher.py:19-28` (`EventData`) expose only event_type/aggregate_id/payload/
source/message_id — **no field carries the producer's outbox row id.**

**Why it bites.** learning-service cannot populate `origin_event_id` from the
outbox row id — that value never arrives. The `ON CONFLICT` guarantee, the
"redelivery is safe" claim, and the sequential-redelivery VERIFY item (line 310)
all rest on an absent field. This is the captured rule "a spec that says
'mirrors X' must PIN X's contract" — the spec named the relay contract instead
of pinning the XADD field set, and the depended-on field is missing.

**Fix (decide at DESIGN):** add `"outbox_id": idStr` to the relay XAdd Values
(outbox_relay.go:159), thread through `_parse_event`/`EventData`, define
`origin_event_id = outbox_id`; this touches the SHARED relay (chapter/chat/
glossary) so it is in B's scope, not free. Add a relay regression-lock test
(`outbox_relay_test.go`) asserting the field is shipped.

---

## F2 — BLOCK — `aggregate_id` is not a per-event id; using it collapses corrections

**Design claim / trap.** With F1 leaving the row id off the wire, the only
per-message id the consumer gets (besides Redis message_id) is `aggregate_id`,
which the outbox keys to the TARGET node id, not the event.

**Evidence.** `glossary-service/internal/api/outbox.go:135-153`:
`insertEntityOutboxEvent` writes `VALUES ('glossary', $1=entityID, ...)` — every
`glossary.entity_updated` for the same entity carries `aggregate_id = entityID`.
KS outbox ("verbatim from glossary shape", §6.1) will do the same. So rename →
re-kind → fix-alias on one entity = three messages with identical
`(origin_service, aggregate_id)`.

**Why it bites.** If BUILD wires `origin_event_id := aggregate_id` (the obvious
shortcut, and §1 line 45 points right at the relay columns), the UNIQUE + ON
CONFLICT DO NOTHING **silently drops the 2nd/3rd correction of every target**.
The correction log — whose value is the SEQUENCE of before→after diffs feeding
eval-gold (plan §2.1/§2.3) — degenerates to one row per target. Invisible in the
happy-path live-smoke (line 311 edits each entity once); surfaces only on the
SECOND edit ("test sequential writes when state-affecting" lesson). Also the
relay `published_at` UPDATE (outbox_relay.go:180) is unguarded best-effort after
XADD — a crash between XADD and UPDATE re-ships the row next tick with a NEW
message_id, so message_id alone does not dedup producer re-emission either; only
a stable outbox-row id does.

**Fix.** Resolve F1, then have the spec EXPLICITLY forbid
`origin_event_id := aggregate_id`, and add a §11 test: two corrections to the
SAME entity ⇒ TWO rows; redelivery of the SAME outbox row ⇒ ONE row.

---

## F3 — WARN — predicate_fix that moves an endpoint can collide with an existing edge id

**Design claim.** §6.4: invalidate-then-recreate;
`invalidate_relation(old)` + `create_relation(new, source_type="manual",
confidence=1.0, pending_validation=false)`; capture before=old / after=new.
Asserts "predicate/endpoint change is structurally a new edge — confirmed."

**Evidence.** `relation_id(user, subject, predicate, object)` hashes all four
(`sdks/python/loreweave_extraction/canonical.py:164-195`). `create_relation`
MERGEs on that id with **ON MATCH** semantics (`relations.py:161-201`): an
existing edge with the derived id is NOT recreated — it runs `ON MATCH SET`
(max-confidence, adopts new pending_validation), and critically the `ON MATCH
SET` branch (lines 183-197) does **NOT** clear `valid_until`.

**Why it bites.** "New edge" holds only when the resulting tuple is novel.
(1) Re-pointing `(Kai,loyal_to,WrongLord)`→`(Kai,loyal_to,RealLord)` when
`(Kai,loyal_to,RealLord)` already exists (incl. a previously-invalidated one)
MERGEs onto that edge, leaving `valid_until` set — the captured `after` describes
a foreign/still-dead edge, not the user's intent. (2) Correcting A→B then B→A
MERGEs the second onto the edge the first invalidated (same id), promoting in
place. The §3 `merge`/`predicate-fix` diff_class assumes a clean two-edge
transition; the live graph can be mutated in a way the log misrepresents.

**Fix.** Pin recreate semantics: after invalidate, detect an existing target-id
edge and decide explicitly (reject, or re-validate by clearing `valid_until` in
the same write — it is NOT in `_CREATE_RELATION_CYPHER` ON MATCH SET today), and
capture `after` from a RE-READ of post-write edge state, never the request
payload. Test: correct an endpoint onto an already-existing tuple ⇒ assert no
silent merge / leftover `valid_until`.

---

Captured rules: read pre-loaded; Guardrails relevant: none (pass:true).
