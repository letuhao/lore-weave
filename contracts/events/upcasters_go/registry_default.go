package upcastersgo

// DefaultRegistry returns a Registry with EVERY shipped upcaster registered.
//
// This is the canonical "register all" the module previously lacked — service
// init code can use it directly instead of hand-registering each upcaster, and
// the S4 conformance test asserts it covers every multi-version hop declared in
// contracts/events/_registry.yaml. When a new version bump ships an upcaster,
// register it HERE; the conformance coverage test fails until you do.
//
// The set is intentionally hand-maintained (one Register line per upcaster) so
// adding a hop is a deliberate, reviewable act — there is no reflection/codegen
// magic that could silently include or omit one.
func DefaultRegistry() *Registry {
	r := NewRegistry()
	r.Register("npc.said", NpcSaidV1ToV2Upcaster())
	return r
}
