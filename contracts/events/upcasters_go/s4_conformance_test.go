package upcastersgo

// S4 (foundation runtime test plan) — upcaster conformance.
//
// Two assertions, both fed by contracts/events/_registry.yaml (the authoritative
// event-schema registry, I14):
//
//  1. RoundTrips — the shipped reference upcaster (npc.said v1→v2) actually
//     transforms a payload through DefaultRegistry.
//  2. Coverage — EVERY multi-version hop the registry declares has a registered
//     upcaster in DefaultRegistry. A new version bump that lands in _registry.yaml
//     without wiring its upcaster fails this test (the drift lock). The signal is
//     `versions` (consecutive pairs need a hop), cross-checked against the
//     `deprecations[].upcaster_to` annotation.
//
// Run as the conformance catalog's `upcaster-conformance` go-test case (no stack).

import (
	"os"
	"path/filepath"
	"testing"

	"gopkg.in/yaml.v3"
)

// registryFile is the minimal projection of _registry.yaml this test reasons about.
type registryFile struct {
	Events []struct {
		Name         string   `yaml:"name"`
		Versions     []uint32 `yaml:"versions"`
		Deprecations []struct {
			Version    uint32 `yaml:"version"`
			UpcasterTo uint32 `yaml:"upcaster_to"`
		} `yaml:"deprecations"`
	} `yaml:"events"`
}

func loadRegistry(t *testing.T) registryFile {
	t.Helper()
	// The test runs from the module dir (contracts/events/upcasters_go); the
	// registry is one level up.
	path := filepath.Join("..", "_registry.yaml")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	var rf registryFile
	if err := yaml.Unmarshal(raw, &rf); err != nil {
		t.Fatalf("parse %s: %v", path, err)
	}
	if len(rf.Events) == 0 {
		t.Fatalf("%s parsed to zero events — wrong path or shape?", path)
	}
	return rf
}

func TestS4UpcasterRoundTrips(t *testing.T) {
	out, err := DefaultRegistry().Upcast("npc.said", map[string]any{"text": "hi"}, 1, 2)
	if err != nil {
		t.Fatalf("npc.said v1→v2 via DefaultRegistry: %v", err)
	}
	if out["tone"] != "neutral" {
		t.Errorf("expected tone=neutral injected, got %v", out["tone"])
	}
	if out["text"] != "hi" {
		t.Errorf("preserved field lost: %v", out)
	}
}

// TestS4UpcasterCoverage asserts every multi-version hop declared in
// _registry.yaml is covered by DefaultRegistry — a missing upcaster (the drift
// we guard against) surfaces as IsMissingUpcaster. An upcaster that exists but
// errors on the empty probe payload is NOT a coverage gap (it's registered), so
// only IsMissingUpcaster fails the case.
func TestS4UpcasterCoverage(t *testing.T) {
	rf := loadRegistry(t)
	reg := DefaultRegistry()

	hops := 0
	for _, e := range rf.Events {
		// Consistency: a declared upcaster_to must be a real, forward version.
		for _, d := range e.Deprecations {
			if d.UpcasterTo == 0 {
				continue
			}
			if d.UpcasterTo <= d.Version {
				t.Errorf("%s: deprecations.upcaster_to %d must be > version %d", e.Name, d.UpcasterTo, d.Version)
			}
			if !containsVersion(e.Versions, d.UpcasterTo) {
				t.Errorf("%s: deprecations.upcaster_to %d not in versions %v", e.Name, d.UpcasterTo, e.Versions)
			}
		}
		// Every consecutive version pair is a hop that must be registered.
		// NOTE: assumes `versions` is consecutive (e.g. [1,2,3]); a gap like
		// [1,3] (version 2 retired mid-chain) would flag a 1→2 hop the registry
		// legitimately lacks. Versions are [1]/[1,2] today; revisit if a version
		// is ever retired from the middle of a live chain.
		for i := 0; i+1 < len(e.Versions); i++ {
			from, to := e.Versions[i], e.Versions[i+1]
			_, err := reg.Upcast(e.Name, map[string]any{}, from, to)
			if err != nil && IsMissingUpcaster(err) {
				t.Errorf("%s: no upcaster registered for hop v%d→v%d (declared in _registry.yaml; add it to DefaultRegistry)", e.Name, from, to)
			}
			hops++
		}
	}
	// Guard the guard: if the registry ever parses to zero multi-version hops,
	// this test would pass vacuously. npc.said (v1→v2) is the shipped baseline.
	if hops == 0 {
		t.Fatal("no multi-version hops found in _registry.yaml — expected at least npc.said v1→v2; coverage check would be vacuous")
	}
}

// TestS4UpcasterCoverage_BitesOnMissing is the standing oracle-bite proof: the
// SAME coverage scan run against an EMPTY registry MUST flag the npc.said v1→v2
// hop as missing. Without this, a coverage check that always passes (because the
// registry happens to be complete) could be silently broken — e.g. an inverted
// IsMissingUpcaster condition — and never noticed. Mirrors the S2/C3
// corruption-injection discipline.
func TestS4UpcasterCoverage_BitesOnMissing(t *testing.T) {
	rf := loadRegistry(t)
	empty := NewRegistry() // deliberately registers nothing

	missing := 0
	for _, e := range rf.Events {
		for i := 0; i+1 < len(e.Versions); i++ {
			_, err := empty.Upcast(e.Name, map[string]any{}, e.Versions[i], e.Versions[i+1])
			if err != nil && IsMissingUpcaster(err) {
				missing++
			}
		}
	}
	if missing == 0 {
		t.Fatal("coverage scan found NO missing hops against an empty registry — the check is vacuous or IsMissingUpcaster is broken")
	}
}

func containsVersion(vs []uint32, v uint32) bool {
	for _, x := range vs {
		if x == v {
			return true
		}
	}
	return false
}
