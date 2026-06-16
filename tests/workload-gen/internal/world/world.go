// Package world is the workload generator's world-state model.
//
// As a stream is generated, World tracks every created entity (realities,
// regions, npcs, pcs, sessions) and each aggregate's current version. This is
// what makes generated streams VALID by construction:
//
//   - referential integrity — a generator can only reference (PickRegion, …)
//     an entity it has already created (AddRegion, …); there are no forward or
//     dangling references.
//   - monotonic versions — NextVersion hands out 1,2,3,… per
//     (reality, aggregate_type, aggregate_id), matching the event store's
//     (reality_id, aggregate_type, aggregate_id, aggregate_version) contract.
//   - determinism — all entity ids derive from the seed (a counter + SHA-1
//     namespace), and all random choices draw from one seeded *rand.Rand, so a
//     given (seed, profile) yields a byte-identical stream across runs.
package world

import (
	"fmt"
	"math/rand"

	"github.com/google/uuid"
)

// namespace anchors deterministic entity-id derivation. A fixed UUID so
// detID(seed, kind, ordinal) is stable across runs and machines.
var namespace = uuid.MustParse("a1b2c3d4-0000-4000-8000-000000000000")

type aggKey struct {
	reality uuid.UUID
	aggType string
	aggID   string
}

// World holds the generated world's entity registries, per-aggregate version
// cursors, and the single seeded RNG that drives all choices.
type World struct {
	seed    int64
	rng     *rand.Rand
	counter map[string]uint64 // kind → next ordinal (deterministic id derivation)

	versions  map[aggKey]uint64
	realities []uuid.UUID
	regions   map[uuid.UUID][]string
	npcs      map[uuid.UUID][]string
	pcs       map[uuid.UUID][]string
	sessions  map[uuid.UUID][]string
}

// New builds an empty World seeded for deterministic generation.
func New(seed int64) *World {
	return &World{
		seed:     seed,
		rng:      rand.New(rand.NewSource(seed)),
		counter:  map[string]uint64{},
		versions: map[aggKey]uint64{},
		regions:  map[uuid.UUID][]string{},
		npcs:     map[uuid.UUID][]string{},
		pcs:      map[uuid.UUID][]string{},
		sessions: map[uuid.UUID][]string{},
	}
}

// Rand exposes the single seeded RNG so the generator's own choices draw from
// the same deterministic source as the world's pickers.
func (w *World) Rand() *rand.Rand { return w.rng }

// detID derives a stable UUID for the next entity of the given kind. Counter-
// based (independent of RNG draws) so adding a random pick elsewhere does not
// shift entity ids.
func (w *World) detID(kind string) uuid.UUID {
	n := w.counter[kind]
	w.counter[kind]++
	return uuid.NewSHA1(namespace, fmt.Appendf(nil, "%d/%s/%d", w.seed, kind, n))
}

// AddReality creates and registers a new reality, returning its id.
func (w *World) AddReality() uuid.UUID {
	id := w.detID("reality")
	w.realities = append(w.realities, id)
	w.regions[id] = nil
	w.npcs[id] = nil
	w.pcs[id] = nil
	w.sessions[id] = nil
	return id
}

// Realities returns the created reality ids in creation order.
func (w *World) Realities() []uuid.UUID { return w.realities }

// NewEventID returns the next deterministic event id. Events are not entities,
// but they share the same seed-derived id factory so a given (seed, profile)
// yields byte-identical event ids across runs.
func (w *World) NewEventID() uuid.UUID { return w.detID("event") }

// AddRegion / AddNpc / AddPc / AddSession register a new entity under a reality
// (which MUST already exist) and return its id.
func (w *World) AddRegion(reality uuid.UUID) string  { return w.add(reality, "region", w.regions) }
func (w *World) AddNpc(reality uuid.UUID) string     { return w.add(reality, "npc", w.npcs) }
func (w *World) AddPc(reality uuid.UUID) string      { return w.add(reality, "pc", w.pcs) }
func (w *World) AddSession(reality uuid.UUID) string { return w.add(reality, "session", w.sessions) }

func (w *World) add(reality uuid.UUID, kind string, reg map[uuid.UUID][]string) string {
	if _, ok := reg[reality]; !ok {
		panic(fmt.Sprintf("world: AddX for unknown reality %s (AddReality first)", reality))
	}
	id := w.detID(kind).String()
	reg[reality] = append(reg[reality], id)
	return id
}

// PickRegion / PickNpc / PickPc / PickSession return a random already-created
// entity id under the reality, or ("", false) if none exists yet. Pickers never
// return an entity that was not created — that is the no-forward-reference
// guarantee.
func (w *World) PickRegion(reality uuid.UUID) (string, bool)  { return w.pick(w.regions[reality]) }
func (w *World) PickNpc(reality uuid.UUID) (string, bool)     { return w.pick(w.npcs[reality]) }
func (w *World) PickPc(reality uuid.UUID) (string, bool)      { return w.pick(w.pcs[reality]) }
func (w *World) PickSession(reality uuid.UUID) (string, bool) { return w.pick(w.sessions[reality]) }

func (w *World) pick(ids []string) (string, bool) {
	if len(ids) == 0 {
		return "", false
	}
	return ids[w.rng.Intn(len(ids))], true
}

// NextVersion returns the next monotonic aggregate_version (1,2,3,…) for an
// aggregate, bumping the cursor.
func (w *World) NextVersion(reality uuid.UUID, aggType, aggID string) uint64 {
	k := aggKey{reality, aggType, aggID}
	w.versions[k]++
	return w.versions[k]
}
