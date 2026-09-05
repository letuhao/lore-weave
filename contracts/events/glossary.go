package events

// glossary.* events — T30 registry adoption (OD-1, PO 2026-08-12).
//
// WHY THIS FILE EXISTS, AND WHY IT IS NOT canon.go
// ------------------------------------------------
// `D-GLOSSARY-EVENTS-NO-SOT` recorded the disease precisely: the authoritative list of
// `glossary.*` event names was a set of Go `const` declarations inside glossary-service,
// **hand-mirrored by five consumers across four services**, with no generator and no gate.
// T30 shipped the gate (`scripts/glossary-events-ssot-gate.py`), which made a producer
// rename fail loudly instead of silently. It did not remove the mirroring.
//
// `canon.go` is the precedent for registering glossary-service's events here, and it says in
// capitals: ***"THIS FILE DOES NOT MODIFY services/glossary-service/."*** Registering these
// seven the same way would have added a SIXTH parallel list on top of the five — the
// deferral's own disease with a YAML file over it. That is why T30's registry half was
// escalated rather than done, and the PO's answer (OD-1, 2026-08-12) was **do the real
// adoption**: one owner of the names, IMPORTED by the producer and by every consumer.
//
// So this file deliberately goes further than canon.go: it modifies glossary-service, and
// the names below are the ones the producer and all five consumers now import. The
// hand-mirroring is what is being deleted; registering the structs is only the price of
// entry (`contracts/events/registry.go` requires a non-empty `go_struct` per entry — there
// is no contract-only registration).
//
// FIDELITY: THESE MIRROR THE WIRE, THEY DO NOT REDESIGN IT
// --------------------------------------------------------
// Every field below was read off the producer's existing payload structs
// (`internal/api/outbox.go`, `outbox_lifecycle.go`, `outbox_curation.go`) and keeps the same
// JSON name, the same type and the same `omitempty`. `string` is used where the producer
// sends a string — including for ids — rather than `uuid.UUID`, because these payloads are
// assembled from database text columns and an id is sometimes deliberately EMPTY (a
// system/auto merge sends `actor_id: ""`, which `uuid.UUID` cannot express and would
// silently render as the nil UUID). A contract that "improves" the shape here would not
// describe the events that are actually on the wire, and the consumers parsing them today
// would break.
//
// 7 event types (the plan's prose says nine; the producer declares seven, and the gate
// agrees — the count is corrected here rather than carried forward):
//   - glossary.entity_updated        — create OR update, distinguished by payload `op`
//   - glossary.entity_merged         — merge/unmerge of two entities
//   - glossary.name_confirmed        — a target-language rendering confirmed by a human
//   - glossary.entity_deleted        — soft delete (trash)
//   - glossary.entity_restored       — restore from trash
//   - glossary.entity_purged         — permanent removal after the retention window
//   - glossary.entity_status_changed — curation status transition

// ⚠️ THE EVENT-TYPE NAME CONSTANTS ARE **GENERATED**, NOT DECLARED HERE.
//
// They live in `contracts/events/generated/registry_generated.go` (same package), emitted
// from `_registry.yaml` by eventgen — `EventGlossaryEntityUpdated`, `EventGlossaryEntityMerged`
// and so on, plus the Python equivalents (`EVENT_GLOSSARY_ENTITY_UPDATED`) for the three
// Python consumers.
//
// This file deliberately does NOT declare them, and that is the whole point of OD-1. Writing
// them here would have been the eighth hand-maintained copy of the same seven strings, just
// in a more authoritative-looking place. The registry owns the names; every producer and
// consumer imports them; a rename is a compile error at every Go use site and an ImportError
// at every Python one.
//
// ⚠️ There is no `glossary.entity_created`. Creation is announced as
// `glossary.entity_updated` with payload `op: "created"` — confirmed on the live stream in
// QC-4. T30's gate found two knowledge-service docstrings describing a subscription to an
// event that cannot exist, and three negative tests that legitimately name it ("this event
// must be ignored") while pinning a name that would silently change meaning if it ever
// started being emitted.

// GlossaryEntitySnapshotV1 is the diffable before/after view carried by
// glossary.entity_updated. learning-service splits it into structural (kind) and
// content-hash (name/aliases/short_description) parts at ingest.
type GlossaryEntitySnapshotV1 struct {
	Name             string   `json:"name"`
	Kind             string   `json:"kind"`
	Aliases          []string `json:"aliases"`
	ShortDescription string   `json:"short_description,omitempty"`
}

// @event       glossary.entity_updated
// @version     1
// @aggregate   glossary
// @description A glossary entity was created or updated in glossary-service. The payload
//
//	`op` field ("created" | "updated") distinguishes the two — there is no
//	separate created event. Self-sufficient by design: it carries name, kind,
//	aliases and short_description so knowledge-service's glossary_sync never
//	has to round-trip back to glossary-service.
type GlossaryEntityUpdatedV1 struct {
	BookID           string   `json:"book_id,omitempty"`
	GlossaryEntityID string   `json:"glossary_entity_id"`
	Name             string   `json:"name"`
	Kind             string   `json:"kind"`
	Aliases          []string `json:"aliases"`
	ShortDescription string   `json:"short_description,omitempty"`
	Op               string   `json:"op"`          // "created" | "updated"
	SourceType       string   `json:"source_type"` // "glossary" (authored canon)
	EmittedAt        string   `json:"emitted_at"`  // RFC3339
	// TargetLanguage is set ONLY when the change is specific to one target language (a
	// translation create/update/delete), so the translation-staleness consumer flags just
	// that language. ABSENT means all-language — the conservative prior behaviour, and
	// rolling-deploy safe because an old consumer simply ignores the field.
	TargetLanguage string `json:"target_language,omitempty"`
	// Phase B correction capture (additive; knowledge-service's glossary_sync ignores
	// these). learning-service persists ONLY actor_type == "user" events as corrections.
	ActorType string                    `json:"actor_type"`
	ActorID   string                    `json:"actor_id,omitempty"`
	Before    *GlossaryEntitySnapshotV1 `json:"before,omitempty"`
	After     *GlossaryEntitySnapshotV1 `json:"after,omitempty"`
}

// @event       glossary.entity_merged
// @version     1
// @aggregate   glossary
// @description Two glossary entities were merged, or a previous merge was undone. The
//
//	payload `op` ("merged" | "unmerged") distinguishes them.
type GlossaryEntityMergedV1 struct {
	BookID         string `json:"book_id,omitempty"`
	WinnerEntityID string `json:"winner_glossary_id"`
	LoserEntityID  string `json:"loser_glossary_id"`
	Op             string `json:"op"` // "merged" | "unmerged"
	// ActorID is the merging user. It is EMPTY for a system/auto merge (e.g. dedup), and
	// that emptiness is load-bearing: learning-service's owner-guard skips the event
	// rather than persisting a nil-UUID owner as if a person had done it.
	ActorID   string `json:"actor_id,omitempty"`
	EmittedAt string `json:"emitted_at"`
}

// @event       glossary.name_confirmed
// @version     1
// @aggregate   glossary
// @description A human confirmed the target-language rendering of an entity name. Always
//
//	an actor_type "user" event — these are JWT endpoints, so the confirmation
//	is a human action by construction.
type GlossaryNameConfirmedV1 struct {
	BookID           string `json:"book_id,omitempty"`
	GlossaryEntityID string `json:"glossary_entity_id"`
	SourceName       string `json:"source_name"`   // the entity's authored name (source side)
	Kind             string `json:"kind"`          //
	LanguageCode     string `json:"language_code"` // the confirmed target language
	Value            string `json:"value"`         // the confirmed target rendering
	ActorType        string `json:"actor_type"`    // always "user"
	ActorID          string `json:"actor_id,omitempty"`
	EmittedAt        string `json:"emitted_at"`
}

// GlossaryEntityLifecycleV1 is the shared payload of the three lifecycle events
// (deleted / restored / purged). One struct rather than three: the wire shape is
// identical and the `op` field is what differs, exactly as the producer emits it.
//
// It is registered three times — once per event_type — because the registry maps an
// event_type to a struct, and three names sharing a shape is not the same as one name.
type GlossaryEntityLifecycleV1 struct {
	BookID           string `json:"book_id"`
	GlossaryEntityID string `json:"glossary_entity_id"`
	Op               string `json:"op"` // "deleted" | "restored" | "purged"
	ActorType        string `json:"actor_type"`
	ActorID          string `json:"actor_id,omitempty"`
	EmittedAt        string `json:"emitted_at"`
}

// @event       glossary.entity_deleted
// @version     1
// @aggregate   glossary
// @description A glossary entity was soft-deleted (moved to trash). Reversible: the row
//
//	still exists and glossary.entity_restored undoes it. Downstream stores
//	should hide the entity, not erase it.
type GlossaryEntityDeletedV1 = GlossaryEntityLifecycleV1

// @event       glossary.entity_restored
// @version     1
// @aggregate   glossary
// @description A soft-deleted glossary entity was restored from the trash.
type GlossaryEntityRestoredV1 = GlossaryEntityLifecycleV1

// @event       glossary.entity_purged
// @version     1
// @aggregate   glossary
// @description A glossary entity was permanently removed after its retention window. This
//
//	is the irreversible one: a consumer that merely hides on this event will
//	keep data the author asked to be destroyed.
type GlossaryEntityPurgedV1 = GlossaryEntityLifecycleV1

// @event       glossary.entity_status_changed
// @version     1
// @aggregate   glossary
// @description A glossary entity's curation status moved. Carries BOTH the new status and
//
//	the prior one, so a consumer can act on the TRANSITION rather than
//	re-deriving it from state it may not have seen.
type GlossaryEntityStatusChangedV1 struct {
	BookID           string `json:"book_id"`
	GlossaryEntityID string `json:"glossary_entity_id"`
	Status           string `json:"status"`
	PriorStatus      string `json:"prior_status"`
	ActorType        string `json:"actor_type"`
	ActorID          string `json:"actor_id,omitempty"`
	EmittedAt        string `json:"emitted_at"`
}
