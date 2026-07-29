package events

import (
	"time"

	"github.com/google/uuid"
)

// Reality-aggregate events.
//
// Every annotation block below is consumed by `tools/eventgen` to populate
// the registry + per-language codegen targets. Format:
//
//	// @event       <canonical_name>
//	// @version     <uint>
//	// @aggregate   <aggregate_type>
//	// @description <one-line semantic description; required per R03 §12C.7>
//
// Optional:
//
//	// @upcast      <fromVersion>->this_version
//	// @deprecated  <ISO date when retiring; R03 §12C.5 cooldown applies>

// @event       reality.created
// @version     1
// @aggregate   reality
// @description A new reality (LLM MMO RPG instance) is provisioned and ready
//              for player commands. Emitted exactly once per RealityID lifetime.
type RealityCreatedV1 struct {
	RealityID    uuid.UUID `json:"reality_id"`
	OwnerUserID  uuid.UUID `json:"owner_user_id"`
	Name         string    `json:"name"`
	WorldSeed    string    `json:"world_seed"`
	LocaleSource string    `json:"locale_source"`
	CreatedAt    time.Time `json:"created_at"`
}

// @event       ruleset.epoch_activated
// @version     1
// @aggregate   reality
// @description A reality's ruleset epoch switched; every affected channel
//              commits one of these, appended by that channel's own lease-holding
//              writer (RLS-A14).
//
// PRODUCER IDENTITY vs WHO APPENDS THE ROW — the distinction that makes this
// event possible at all.
//
// RLS-A14 makes this EVT-T8 Administrative and EVT-P8 forbids a non-admin
// emitter, which reads at first like "admin-cli must write the row". It cannot:
// ChannelWriter::append CASes on `channel_writer_state.current_epoch`, so only
// the process holding that channel's WRITER lease may append, and admin-cli
// holds no lease.
//
// The two are not the same claim. `Producer::Admin` records WHO AUTHORISED the
// change — and the authorisation IS a durable admin act: admin-cli writes the
// `reality_ruleset_binding` row (append-only, one row per epoch, audited
// through meta_write). The lease-holder merely TRANSCRIBES that decision into
// its own channel. It cannot invent one: `AuthorisedBy` below pins the binding
// row, and a writer that appended this event without a matching binding would
// be making a claim the meta DB does not support.
//
// WHY N EVENTS AND NOT ONE
//
// One per affected channel, each appended independently by that channel's
// writer. There is no coordination point, which is what RLS-D17 ("no
// reality-wide barrier") requires — and the reason `dp::channel_pause` is not
// needed and does not exist. A single reality-scoped event would have to be
// written by someone, and that someone would be a barrier.
type RulesetEpochActivatedV1 struct {
	RealityID uuid.UUID `json:"reality_id"`
	// The channel this copy was committed to. Two events differing only here
	// describe ONE switch seen by two channels, not two switches.
	ChannelID int64 `json:"channel_id"`
	FromEpoch uint32 `json:"from_epoch"`
	ToEpoch   uint32 `json:"to_epoch"`
	// The resolved ruleset the reality is now bound to: 64 lowercase hex, the
	// one spelling this value has outside Rust.
	Digest string `json:"digest"`
	// The admin act this transcribes — `reality_ruleset_binding(reality_id,
	// epoch)`. Present so an auditor can join the committed event back to the
	// authorisation rather than trusting the writer.
	AuthorisedBy string    `json:"authorised_by"`
	ActivatedAt  time.Time `json:"activated_at"`
}
