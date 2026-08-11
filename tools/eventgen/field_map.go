package main

import (
	"errors"
	"fmt"
	"sort"
	"strings"

	"github.com/loreweave/foundation/contracts/events"
)

// Field describes one struct field across all generated languages.
//
// V1 SCOPE: cycle 8 hand-maintains this map for the 3 seed events. Cycle 12+
// Track 4 will introduce Go AST parsing (see D-EVENTGEN-AST-PARSE deferred).
// Until then, adding a new event = struct in contracts/events/ + entry in
// _registry.yaml + entry in this map.
type Field struct {
	Name       string // snake_case canonical name (matches JSON wire shape)
	GoType     string // for reference / future Go-side reflection
	RustType   string // Rust type expression
	TsType     string // TypeScript type expression
	PythonType string // Python type annotation
}

// fieldsForEvent returns the ordered field list for (eventType, version).
// Order = JSON wire order = struct declaration order in contracts/events/.
//
// Returns nil for an event with no map. **That used to be silent**, and the
// comment here used to claim the emitters wrote a `// TODO: field map missing`
// marker "so the gap is visible". They did not — no emitter has ever written
// that string. An event with no map generated `pub struct X {}`,
// `export interface X {}` and an empty Pydantic model, in three languages, with
// no warning anywhere.
//
// It shipped on 2026-07-30: `ruleset.epoch_activated` was added to the registry
// with a 7-field Go struct and no map row, and the codegen emitted three empty
// shells that a consumer would have imported as the contract. The description
// of the safety net was the only thing standing where the net should have been.
//
// The gap is now enforced by [noFieldMapAllowed] — see its comment.
func fieldsForEvent(eventType string, version uint32) []Field {
	switch eventType {
	case "channel.turn_boundary":
		if version == 1 {
			return []Field{
				// turn_number IS a CWC-A2 decimal-string case, and this file
				// already said so before the field existed: the note on
				// `channel_id` below names "turn_number, island_seq,
				// channel_event_id" as the monotonic counters the rule is FOR.
				// contracts/game-wire/README.md agrees. So the TS type is
				// `string`, not `number` — JS corrupts past 2^53, and the bug
				// is invisible in dev because small values round-trip fine.
				{"turn_number", "uint64", "u64", "string", "int"},
				// The FIRST opaque-JSON field in this map. DP-Ch21 is explicit
				// that DP does not interpret turn_data: it is a D&D round, a
				// scene title, "player A's turn" — vocabulary owned by whichever
				// feature advances turns. Giving it a schema here would make the
				// data plane the owner of a domain language, which is the
				// D-2 shape (game vocabulary in engine tables).
				{"turn_data", "json.RawMessage", "serde_json::Value", "unknown", "Any"},
			}
		}
	case "ruleset.epoch_activated":
		if version == 1 {
			return []Field{
				{"reality_id", "uuid.UUID", "Uuid", "string", "str"},
				// int64, and NOT a CWC-A2 decimal-string case. That rule exists
				// for monotonic counters that genuinely grow past 2^53 —
				// turn_number, island_seq, channel_event_id. A channel id is a
				// small per-reality index, and rendering it as a string here
				// would make the TS type disagree with the bytes Go's
				// `encoding/json` actually writes for an `int64` field.
				{"channel_id", "int64", "i64", "number", "int"},
				{"from_epoch", "uint32", "u32", "number", "int"},
				{"to_epoch", "uint32", "u32", "number", "int"},
				{"digest", "string", "String", "string", "str"},
				{"authorised_by", "string", "String", "string", "str"},
				{"activated_at", "time.Time", "chrono::DateTime<chrono::Utc>", "string", "datetime"},
			}
		}
	case "reality.created":
		if version == 1 {
			return []Field{
				{"reality_id", "uuid.UUID", "Uuid", "string", "str"},
				{"owner_user_id", "uuid.UUID", "Uuid", "string", "str"},
				{"name", "string", "String", "string", "str"},
				{"world_seed", "string", "String", "string", "str"},
				{"locale_source", "string", "String", "string", "str"},
				{"created_at", "time.Time", "chrono::DateTime<chrono::Utc>", "string", "datetime"},
			}
		}
	case "npc.said":
		if version == 1 {
			return []Field{
				{"npc_id", "uuid.UUID", "Uuid", "string", "str"},
				{"text", "string", "String", "string", "str"},
				{"scene_id", "uuid.UUID", "Uuid", "string", "str"},
				{"said_at", "time.Time", "chrono::DateTime<chrono::Utc>", "string", "datetime"},
			}
		}
		if version == 2 {
			return []Field{
				{"npc_id", "uuid.UUID", "Uuid", "string", "str"},
				{"text", "string", "String", "string", "str"},
				{"scene_id", "uuid.UUID", "Uuid", "string", "str"},
				{"said_at", "time.Time", "chrono::DateTime<chrono::Utc>", "string", "datetime"},
				{"tone", "string", "String", "string", "str"},
			}
		}
	case "world.tick":
		if version == 1 {
			return []Field{
				{"reality_id", "uuid.UUID", "Uuid", "string", "str"},
				{"tick_index", "uint64", "u64", "number", "int"},
				{"tick_at", "time.Time", "chrono::DateTime<chrono::Utc>", "string", "datetime"},
			}
		}
	// canon.* — RAID cycle 23 L5.A. Per Q-L5A-1 foundation owns ONLY the
	// schema; glossary-service outbox emitter is a separate sub-program.
	// Field maps included here so the polyglot codegen produces a usable
	// shape for the contract-test fixture and downstream meta-worker writer
	// in cycle 24+. `value` / `old_value` / `new_value` are emitted as
	// opaque byte slices on the Go side and (for now) opaque strings in
	// polyglot targets — Q-L5-3 single-table projection writer parses JSON.
	case "canon.entry.created":
		if version == 1 {
			return []Field{
				{"canon_entry_id", "uuid.UUID", "Uuid", "string", "str"},
				{"book_id", "uuid.UUID", "Uuid", "string", "str"},
				{"attribute_path", "string", "String", "string", "str"},
				{"value", "[]byte", "Vec<u8>", "string", "bytes"},
				{"canon_layer", "string", "String", "string", "str"},
				{"lock_level", "string", "String", "string", "str"},
				{"author_user_id", "uuid.UUID", "Uuid", "string", "str"},
				{"created_at", "time.Time", "chrono::DateTime<chrono::Utc>", "string", "datetime"},
			}
		}
	case "canon.entry.updated":
		if version == 1 {
			return []Field{
				{"canon_entry_id", "uuid.UUID", "Uuid", "string", "str"},
				{"book_id", "uuid.UUID", "Uuid", "string", "str"},
				{"attribute_path", "string", "String", "string", "str"},
				{"old_value", "[]byte", "Vec<u8>", "string", "bytes"},
				{"new_value", "[]byte", "Vec<u8>", "string", "bytes"},
				{"canon_layer", "string", "String", "string", "str"},
				{"editor_user_id", "uuid.UUID", "Uuid", "string", "str"},
				{"updated_at", "time.Time", "chrono::DateTime<chrono::Utc>", "string", "datetime"},
			}
		}
	case "canon.entry.promoted":
		if version == 1 {
			return []Field{
				{"canon_entry_id", "uuid.UUID", "Uuid", "string", "str"},
				{"book_id", "uuid.UUID", "Uuid", "string", "str"},
				{"from_layer", "string", "String", "string", "str"},
				{"to_layer", "string", "String", "string", "str"},
				{"promoted_by", "uuid.UUID", "Uuid", "string", "str"},
				{"promoted_at", "time.Time", "chrono::DateTime<chrono::Utc>", "string", "datetime"},
			}
		}
	case "canon.entry.decanonized":
		if version == 1 {
			return []Field{
				{"canon_entry_id", "uuid.UUID", "Uuid", "string", "str"},
				{"book_id", "uuid.UUID", "Uuid", "string", "str"},
				{"reason", "string", "String", "string", "str"},
				{"decanonized_by", "uuid.UUID", "Uuid", "string", "str"},
				{"decanonized_at", "time.Time", "chrono::DateTime<chrono::Utc>", "string", "datetime"},
			}
		}
	}
	return nil
}

// noFieldMapAllowed lists the (event, version) pairs that are KNOWN to have no
// field map and are permitted to generate an empty struct.
//
// Every one of these predates the check. They are listed, not tolerated: the
// point of the list is that it is *closed*, so the eight existing gaps stay
// exactly eight. An event outside it with no fields fails the generation run
// (see [checkFieldMaps]) rather than quietly producing an empty contract in
// three languages.
//
// The value is the reason the gap is still open, printed on failure. It is not
// decoration — a row with no reason is a row nobody can retire.
var noFieldMapAllowed = map[string]string{
	// canon.* administrative events: the Go structs carry opaque `[]byte`
	// values whose polyglot spelling was left to the projection writer that
	// consumes them (cycle 24+). Mapping them now would guess a shape.
	"admin.canon.override.requested@1":    "cycle 24+ — override payload shape not settled",
	"admin.canon.override.consented@1":    "cycle 24+ — override payload shape not settled",
	"admin.canon.override.vetoed@1":       "cycle 24+ — override payload shape not settled",
	"admin.canon.override.compensating@1": "cycle 24+ — override payload shape not settled",
	"canon.change.recorded@1":             "cycle 24+ — change payload shape not settled",
	// The xreality.* bridge topics re-publish another event's payload, so they
	// have no fields of their own to map.
	"xreality.canon.promoted@1": "bridge topic — republishes canon.entry.promoted's payload",
	"xreality.user.erased@1":    "bridge topic — republishes the meta erasure payload",
}

// fieldMapKey is the allowlist key: `<event>@<version>`. Versioned because a
// v2 can add fields a v1 map does not have, and an allowlist keyed on the event
// alone would exempt every future version of it — the NV-3 shape, where the
// scope silently widens past what anyone agreed to.
func fieldMapKey(eventType string, version uint32) string {
	return fmt.Sprintf("%s@%d", eventType, version)
}

// checkFieldMaps fails the generation run if the field-map coverage has drifted
// in EITHER direction.
//
// Both directions, and the second one is the half that keeps the list honest:
//
//   - an event with **no** map that is **not** allowlisted — the new-event case,
//     which is what shipped empty structs for `ruleset.epoch_activated`;
//   - an allowlisted event that **now has** a map — the shrink rule. Without it
//     the list only ever grows, and a stale exemption reads as coverage to
//     everyone after you. Same discipline as `gate-wiring-gate`'s KNOWN_RED and
//     `deferral-gate`'s PROSE_ONLY rows.
//
// It runs inside `Run`, before any emitter, so a bad state cannot reach disk at
// all — the files a reviewer looks at are never the empty ones.
func checkFieldMaps(reg *events.Registry) error {
	var missing, stale []string
	seen := map[string]bool{}
	for _, name := range reg.EventTypes() {
		e, err := reg.LookupType(name)
		if err != nil {
			return fmt.Errorf("look up %s: %w", name, err)
		}
		for _, v := range e.Versions {
			key := fieldMapKey(e.Name, v)
			seen[key] = true
			has := len(fieldsForEvent(e.Name, v)) > 0
			_, exempt := noFieldMapAllowed[key]
			switch {
			case !has && !exempt:
				missing = append(missing, key)
			case has && exempt:
				stale = append(stale, key)
			}
		}
	}
	// An allowlist row whose event left the registry entirely: also stale.
	for key := range noFieldMapAllowed {
		if !seen[key] {
			stale = append(stale, key+" (no longer in the registry)")
		}
	}
	sort.Strings(missing)
	sort.Strings(stale)

	var b strings.Builder
	if len(missing) > 0 {
		b.WriteString("eventgen: these events have NO field map, so every language would\n")
		b.WriteString("emit an EMPTY struct that a consumer imports as the contract:\n")
		for _, k := range missing {
			b.WriteString("    " + k + "\n")
		}
		b.WriteString("Add the fields to fieldsForEvent in tools/eventgen/field_map.go.\n")
	}
	if len(stale) > 0 {
		b.WriteString("eventgen: these noFieldMapAllowed rows are STALE — the gap they\n")
		b.WriteString("excuse no longer exists, and an exemption that outlives its reason\n")
		b.WriteString("reads as coverage. Delete them:\n")
		for _, k := range stale {
			b.WriteString("    " + k + "\n")
		}
	}
	if b.Len() > 0 {
		return errors.New(strings.TrimRight(b.String(), "\n"))
	}
	return nil
}
