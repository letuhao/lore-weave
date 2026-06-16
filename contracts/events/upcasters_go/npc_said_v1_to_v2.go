package upcastersgo

// NpcSaidV1ToV2 is the shipped reference upcaster for the seed registry's
// only multi-version event. Adds a `tone` field defaulting to "neutral".
//
// Wire-equivalent to the Rust `crates/dp-kernel/src/upcaster.rs` tests'
// `npc_said_v1_to_v2`. Keep these byte-equivalent across language ports.
func NpcSaidV1ToV2(payload map[string]any) (map[string]any, error) {
	out := make(map[string]any, len(payload)+1)
	for k, v := range payload {
		out[k] = v
	}
	if _, exists := out["tone"]; !exists {
		out["tone"] = "neutral"
	}
	return out, nil
}

// NpcSaidV1ToV2Upcaster returns the registry-ready Upcaster wrapper. Service
// init code does:
//
//	reg.Register("npc.said", NpcSaidV1ToV2Upcaster())
func NpcSaidV1ToV2Upcaster() Upcaster {
	return &FnUpcaster{From: 1, Fn: NpcSaidV1ToV2}
}
