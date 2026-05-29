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
