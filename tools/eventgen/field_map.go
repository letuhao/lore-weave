package main

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
// Returns empty slice for unknown (type, version) — emitter then writes a
// `// TODO: field map missing` comment so the gap is visible.
func fieldsForEvent(eventType string, version uint32) []Field {
	switch eventType {
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
	}
	return nil
}
