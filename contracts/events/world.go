package events

import (
	"time"

	"github.com/google/uuid"
)

// World-aggregate events.

// @event       world.tick
// @version     1
// @aggregate   world
// @description Periodic in-world heartbeat (every N real-world seconds).
//              Drives scheduled NPC behaviors, weather, faction simulation.
type WorldTickV1 struct {
	RealityID uuid.UUID `json:"reality_id"`
	TickIndex uint64    `json:"tick_index"`
	TickAt    time.Time `json:"tick_at"`
}
