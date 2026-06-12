package events

import (
	"time"

	"github.com/google/uuid"
)

// NPC-aggregate events.
//
// `npc.said` is the canonical "NPC utterance" event. It has TWO versions to
// exercise the L2.H upcaster chain in tests:
//
//   - V1: bare (npc_id, text, scene_id)
//   - V2: adds `tone` ("neutral", "angry", "playful", ...) — added during the
//     2026-07 LLM-safety sub-program for safety-classifier inputs. v1 events
//     upcast with tone="neutral" default.

// @event       npc.said
// @version     1
// @aggregate   npc
// @description NPC utters a line of dialogue in-world.
// @deprecated  2026-12-31
type NpcSaidV1 struct {
	NpcID    uuid.UUID `json:"npc_id"`
	Text     string    `json:"text"`
	SceneID  uuid.UUID `json:"scene_id"`
	SaidAt   time.Time `json:"said_at"`
}

// @event       npc.said
// @version     2
// @aggregate   npc
// @description NPC utters a line of dialogue in-world; v2 adds @tone for the
//              LLM-safety pipeline.
// @upcast      1->2
type NpcSaidV2 struct {
	NpcID    uuid.UUID `json:"npc_id"`
	Text     string    `json:"text"`
	SceneID  uuid.UUID `json:"scene_id"`
	SaidAt   time.Time `json:"said_at"`
	Tone     string    `json:"tone"` // "neutral" default; upcaster fills v1 events with "neutral"
}
