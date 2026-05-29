package events

import (
	"time"

	"github.com/google/uuid"
)

// xreality.* events — RAID cycle 10, L2.L.
//
// These events emit through the normal per-reality outbox + publisher flow
// AND additionally fan out to the `xreality.<entity>.<verb>` Redis Stream
// (Q-L2-4 naming) where meta-worker (sole consumer per I7) dispatches them.
//
// The fanout is selected by `Envelope.Metadata["cross_reality"] = true`. The
// emitting service MUST set the flag; the L2.F validator accepts xreality
// events like any other registered event_type (no special validation path).
//
// Annotation format matches `reality.go` / `npc.go` / `world.go` — consumed
// by `tools/eventgen` to populate the registry + polyglot codegen.

// @event       xreality.canon.promoted
// @version     1
// @aggregate   reality
// @description A canon entry was promoted in one reality; meta-worker
//              dispatches projection writes across consumer realities.
type XRealityCanonPromotedV1 struct {
	SourceRealityID uuid.UUID `json:"source_reality_id"`
	EntryID         string    `json:"entry_id"`
	EntryType       string    `json:"entry_type"`
	PromotedBy      uuid.UUID `json:"promoted_by"`
	PromotedAt      time.Time `json:"promoted_at"`
}

// @event       xreality.user.erased
// @version     1
// @aggregate   reality
// @description GDPR erasure event for a user; meta-worker fans out the
//              deletion to every reality the user touched.
type XRealityUserErasedV1 struct {
	UserID    uuid.UUID `json:"user_id"`
	ErasedAt  time.Time `json:"erased_at"`
	RequestID string    `json:"request_id"`
}
