// Package gen is the seeded workload generator's engine.
//
// Generate produces a causally-valid, deterministic event stream for a profile:
// it drives world-state (package world) so every reference resolves to an
// already-created entity, assigns monotonic per-aggregate versions, and stamps
// seed-derived ids + a logical clock (never wall-clock). A given (seed, profile)
// yields a byte-identical stream across runs — the precondition for the spine's
// deterministic-replay property.
//
// Validate is the independent referential+causal checker (the acceptance proof):
// it re-walks a stream and rejects any non-contiguous version or forward/
// dangling reference.
package gen

import (
	"fmt"
	"time"

	"github.com/google/uuid"

	events "github.com/loreweave/foundation/contracts/events"
	"github.com/loreweave/foundation/tests/workload-gen/internal/schema"
	"github.com/loreweave/foundation/tests/workload-gen/internal/world"
)

// Stream is an ordered, causally-valid event stream.
type Stream = []events.Envelope

// baseEpoch anchors the logical clock — a FIXED time (never wall-clock) so a
// given (seed, profile) yields byte-identical timestamps across runs.
var baseEpoch = time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)

// Profile parameterizes a generated workload's shape.
type Profile struct {
	Name                   string
	Realities              int
	RegionsPerReality      int
	NpcsPerReality         int
	PcsPerReality          int
	SessionsPerReality     int
	SaysPerSession         int
	ParticipantsPerSession int
	CanonEntries           int
}

// Profiles is the catalog of the 4 plan profiles (§5).
var Profiles = map[string]Profile{
	"micro":              {Name: "micro", Realities: 1, RegionsPerReality: 1, NpcsPerReality: 1, SessionsPerReality: 1, SaysPerSession: 1},
	"single-reality":     {Name: "single-reality", Realities: 1, RegionsPerReality: 3, NpcsPerReality: 4, PcsPerReality: 2, SessionsPerReality: 2, SaysPerSession: 3, ParticipantsPerSession: 1, CanonEntries: 2},
	"multi-reality":      {Name: "multi-reality", Realities: 3, RegionsPerReality: 2, NpcsPerReality: 3, PcsPerReality: 2, SessionsPerReality: 2, SaysPerSession: 2, ParticipantsPerSession: 1, CanonEntries: 1},
	"multi-user-session": {Name: "multi-user-session", Realities: 1, RegionsPerReality: 2, NpcsPerReality: 2, PcsPerReality: 5, SessionsPerReality: 4, SaysPerSession: 2, ParticipantsPerSession: 3},
}

// Generator assembles a deterministic event stream.
type Generator struct {
	w     *world.World
	clock time.Time
	misc  uint64 // counter for deterministic external/scalar values
}

// New builds a Generator seeded for deterministic generation.
func New(seed int64) *Generator {
	return &Generator{w: world.New(seed), clock: baseEpoch}
}

func (g *Generator) tick() time.Time {
	t := g.clock
	g.clock = g.clock.Add(time.Second)
	return t
}

func (g *Generator) nextMisc() uint64 { g.misc++; return g.misc }

// extID derives a deterministic id for an entity that lives outside our world
// (a glossary entity, a user, a book, a canon entry).
func (g *Generator) extID(kind string) string {
	return uuid.NewSHA1(uuid.Nil, fmt.Appendf(nil, "%s-%d", kind, g.nextMisc())).String()
}

// emit builds one envelope, advancing the clock, the event id, and the
// aggregate's version cursor.
func (g *Generator) emit(reality uuid.UUID, aggType, aggID, eventType string, payload schema.Payload, metadata map[string]any) events.Envelope {
	t := g.tick()
	return events.Envelope{
		EventID:          g.w.NewEventID(),
		EventType:        eventType,
		EventVersion:     1,
		AggregateID:      aggID,
		AggregateType:    aggType,
		AggregateVersion: g.w.NextVersion(reality, aggType, aggID),
		RealityID:        reality,
		OccurredAt:       t,
		RecordedAt:       t,
		Payload:          payload,
		Metadata:         metadata,
	}
}

var moods = []string{"calm", "wary", "cheerful", "sullen"}

// embedding1536 returns a deterministic EmbeddingDim-length vector. The
// NpcSessionMemoryEmbedding projection requires dim=1536 + a 1536-element
// embedding (the VECTOR(1536) / BYTEA fallback column), so the value content is
// irrelevant — only the length matters. Fixed so streams stay byte-deterministic.
func embedding1536() []float64 {
	v := make([]float64, schema.EmbeddingDim)
	for i := range v {
		v[i] = 0.1
	}
	return v
}

// Generate produces the full deterministic stream for a profile.
func (g *Generator) Generate(p Profile) Stream {
	var s Stream
	rng := g.w.Rand()

	for ri := 0; ri < p.Realities; ri++ {
		reality := g.w.AddReality()

		// regions — no references.
		for i := 0; i < p.RegionsPerReality; i++ {
			id := g.w.AddRegion(reality)
			code := fmt.Sprintf("r%d", g.nextMisc())
			s = append(s, g.emit(reality, "region", id, "region.created", schema.RegionCreated(code, "Region "+code), nil))
		}
		// npcs — spawn in an existing region.
		for i := 0; i < p.NpcsPerReality; i++ {
			id := g.w.AddNpc(reality)
			region, ok := g.w.PickRegion(reality)
			if !ok {
				region = g.w.AddRegion(reality)
				s = append(s, g.emit(reality, "region", region, "region.created", schema.RegionCreated("rx", "Region rx"), nil))
			}
			s = append(s, g.emit(reality, "npc", id, "npc.created", schema.NpcCreated(g.extID("glossary"), region, moods[rng.Intn(len(moods))]), nil))
		}
		// pcs — spawn in a region, then maybe move.
		for i := 0; i < p.PcsPerReality; i++ {
			id := g.w.AddPc(reality)
			region, _ := g.w.PickRegion(reality)
			s = append(s, g.emit(reality, "pc", id, "pc.spawned", schema.PcSpawned(g.extID("user"), fmt.Sprintf("PC-%d", g.misc), region), nil))
			if to, ok := g.w.PickRegion(reality); ok && to != region {
				s = append(s, g.emit(reality, "pc", id, "pc.moved", schema.PcMoved(to), nil))
			}
		}
		// sessions — started → participant_joined* → npc.said* → ended.
		for i := 0; i < p.SessionsPerReality; i++ {
			npc, ok := g.w.PickNpc(reality)
			if !ok {
				continue // no npc to host a session
			}
			sid := g.w.AddSession(reality)
			s = append(s, g.emit(reality, "session", sid, "session.started", schema.SessionStarted(npc, sid), nil))
			for j := 0; j < p.ParticipantsPerSession; j++ {
				pc, ok := g.w.PickPc(reality)
				if !ok {
					break
				}
				s = append(s, g.emit(reality, "session", sid, "session.participant_joined", schema.SessionParticipantJoined(sid, "pc", pc), nil))
			}
			for k := 0; k < p.SaysPerSession; k++ {
				s = append(s, g.emit(reality, "npc", npc, "npc.said", schema.NpcSaid(fmt.Sprintf("line %d", g.nextMisc())), map[string]any{"session_id": sid}))
			}
			// W3.1 — on the FIRST session, emit the two npc events that previously
			// got 0 coverage (un-vacuums npc_pc_relationship_projection +
			// npc_session_memory_embedding). Once per reality keeps the streams
			// (and the 1536-float embedding) from bloating every session. The
			// hosting npc + this session are live here; the relationship also
			// needs a pc.
			if i == 0 {
				if pc, okPc := g.w.PickPc(reality); okPc {
					s = append(s, g.emit(reality, "npc", npc, "npc.relationship_changed",
						schema.NpcRelationshipChanged(pc, 5, 1, sid, []string{"acquaintance"}), nil))
						// The reciprocal pc→npc relationship: a pc-aggregate event whose
						// projection (pc_relationship_projection) is ALSO an Upsert (created
						// on the first relationship_changed), live-exercising the pc side of
						// the upsert fix (D-W3-NPC-REL-PROJECTION-UPSERT).
						s = append(s, g.emit(reality, "pc", pc, "pc.relationship_changed",
							schema.PcRelationshipChanged("npc", npc, 42, []string{"friendly"}), nil))
				}
				s = append(s, g.emit(reality, "npc", npc, "npc.memory_embedded",
					schema.NpcMemoryEmbedded(npc, sid, "mem-"+sid, embedding1536()), nil))
			}
			s = append(s, g.emit(reality, "session", sid, "session.ended", schema.SessionEnded(npc, sid), nil))
		}
		// world kv — set then unset (the DELETE arm) + a PERSISTENT set (W3.1: the
		// row-present arm — set+unset net-zeroes, leaving world_kv_projection with
		// no row to verify, so add a key that is set and never unset).
		key := fmt.Sprintf("flag.%d", g.nextMisc())
		s = append(s, g.emit(reality, "world", "world", "world.kv_set", schema.WorldKvSet(key, true), nil))
		s = append(s, g.emit(reality, "world", "world", "world.kv_unset", schema.WorldKvUnset(key), nil))
		pkey := fmt.Sprintf("persist.%d", g.nextMisc())
		s = append(s, g.emit(reality, "world", "world", "world.kv_set", schema.WorldKvSet(pkey, true), nil))
		// canon — created → updated → promoted (per entry, its own aggregate).
		for i := 0; i < p.CanonEntries; i++ {
			cid := g.extID("canon")
			book := g.extID("book")
			s = append(s, g.emit(reality, "canon", cid, "canon.entry.created", schema.CanonEntryCreated(cid, book, "characters/x/race", "elf", "L2_seeded"), nil))
			s = append(s, g.emit(reality, "canon", cid, "canon.entry.updated", schema.CanonEntryUpdated(cid, "half-elf", "L2_seeded"), nil))
			s = append(s, g.emit(reality, "canon", cid, "canon.entry.promoted", schema.CanonEntryPromoted(cid, "L1_axiom"), nil))
		}
	}
	return s
}

// Validate re-walks a stream and asserts it is internally consistent:
//   - per-aggregate versions are contiguous 1..n (no gap, no decrease);
//   - every reference (spawn_region_id, npc_id, session_id, …) resolves to an
//     entity created EARLIER in the stream — no forward or dangling reference.
//
// It returns the first violation, or nil. This is the independent referential+
// causal proof (plan acceptance), separate from the generator that built the
// stream.
//
// SCOPE: Validate proves the stream is internally consistent at the STREAM
// level. It does NOT guarantee rebuildability for multi-aggregate projection
// tables — e.g. npc.said fans out an update to npc_session_memory_projection (a
// row owned by the session aggregate), which the full-table rebuilder, replaying
// aggregates independently, cannot resolve (it reports aggregates_failed; the
// integrity-checker's multi-aggregate replay-aggregate handles it). A passing
// Validate means "no forward/dangling reference + monotonic versions", not "every
// projection rebuilds clean". See D-REBUILDER-MULTI-AGG.
func Validate(s Stream) error {
	versions := map[string]uint64{} // reality|aggType|aggID → last version
	created := map[string]bool{}    // "kind|reality|id"
	npcSession := map[string]bool{} // "reality|npc|session" — a started session for an npc

	key := func(kind string, r uuid.UUID, id string) string { return kind + "|" + r.String() + "|" + id }

	for i, e := range s {
		vk := e.RealityID.String() + "|" + e.AggregateType + "|" + e.AggregateID
		if e.AggregateVersion != versions[vk]+1 {
			return fmt.Errorf("event %d (%s, agg %s/%s): version %d not contiguous (expected %d)",
				i, e.EventType, e.AggregateType, e.AggregateID, e.AggregateVersion, versions[vk]+1)
		}
		versions[vk] = e.AggregateVersion

		r := e.RealityID
		str := func(k string) string { v, _ := e.Payload[k].(string); return v }
		need := func(kind, id string) error {
			if !created[key(kind, r, id)] {
				return fmt.Errorf("event %d (%s): references %s %q which was not created earlier", i, e.EventType, kind, id)
			}
			return nil
		}

		switch e.EventType {
		case "region.created":
			created[key("region", r, e.AggregateID)] = true
		case "npc.created":
			if err := need("region", str("spawn_region_id")); err != nil {
				return err
			}
			created[key("npc", r, e.AggregateID)] = true
		case "npc.said":
			if err := need("npc", e.AggregateID); err != nil {
				return err
			}
			sid, _ := e.Metadata["session_id"].(string)
			if !npcSession[r.String()+"|"+e.AggregateID+"|"+sid] {
				return fmt.Errorf("event %d npc.said: no started session %q for npc %q", i, sid, e.AggregateID)
			}
		case "npc.relationship_changed":
			// npc-aggregate event referencing a pc the npc relates to.
			if err := need("npc", e.AggregateID); err != nil {
				return err
			}
			if err := need("pc", str("other_entity_id")); err != nil {
				return err
			}
		case "npc.memory_embedded":
			// npc-aggregate event for a session the npc hosted.
			if err := need("npc", e.AggregateID); err != nil {
				return err
			}
			if sid := str("session_id"); !npcSession[r.String()+"|"+e.AggregateID+"|"+sid] {
				return fmt.Errorf("event %d npc.memory_embedded: no started session %q for npc %q", i, sid, e.AggregateID)
			}
		case "pc.spawned":
			if err := need("region", str("spawn_region_id")); err != nil {
				return err
			}
			created[key("pc", r, e.AggregateID)] = true
		case "pc.moved":
			if err := need("pc", e.AggregateID); err != nil {
				return err
			}
			if err := need("region", str("to_region_id")); err != nil {
				return err
			}
		case "session.started":
			if err := need("npc", str("npc_id")); err != nil {
				return err
			}
			created[key("session", r, e.AggregateID)] = true
			npcSession[r.String()+"|"+str("npc_id")+"|"+str("session_id")] = true
		case "session.participant_joined", "session.participant_left":
			if err := need("session", str("session_id")); err != nil {
				return err
			}
		case "session.ended":
			if err := need("session", e.AggregateID); err != nil {
				return err
			}
		case "canon.entry.created":
			created[key("canon", r, e.AggregateID)] = true
		case "canon.entry.updated", "canon.entry.promoted", "canon.entry.decanonized":
			if err := need("canon", e.AggregateID); err != nil {
				return err
			}
		case "pc.relationship_changed":
			// pc-aggregate event referencing another entity (npc or pc) it relates to.
			if err := need("pc", e.AggregateID); err != nil {
				return err
			}
			if err := need(str("other_entity_type"), str("other_entity_id")); err != nil {
				return err
			}
		case "world.kv_set", "world.kv_unset", "region.ambient_changed",
			"pc.item_acquired":
			// no cross-entity reference to resolve (the unset-after-set ordering
			// is guaranteed by construction; world is a singleton aggregate).
		default:
			return fmt.Errorf("event %d: unknown event_type %q (no validation rule)", i, e.EventType)
		}
	}
	return nil
}
