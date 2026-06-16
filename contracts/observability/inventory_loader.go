package observability

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

// LoadMode controls how strictly LoadAndValidate parses the YAML.
type LoadMode int

const (
	// ModeStrict — unknown top-level or per-entry YAML keys are rejected.
	// Use for runtime admission-control loaders so a typo in inventory.yaml
	// fails fast instead of silently no-op'ing.
	ModeStrict LoadMode = iota
	// ModeLax — unknown keys are tolerated (forward-compat). Use for
	// non-admission consumers (e.g., the shell lint that only wants the
	// name set) where a new optional field shouldn't break older readers.
	ModeLax
)

// LoadAndValidate reads + parses inventory.yaml and validates the full
// inventory:
//
//  1. version supported (== 1)
//  2. each Entry.Validate() passes
//  3. no duplicate names
//  4. (strict mode only) no unknown YAML keys
//
// On any failure, the returned Inventory is the partially-loaded zero
// value — callers MUST refuse to serve admission lookups on error
// (silently accepting unregistered emissions defeats the lint).
func LoadAndValidate(path string, mode LoadMode) (Inventory, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return Inventory{}, fmt.Errorf("observability: read inventory: %w", err)
	}
	return ParseAndValidate(raw, mode)
}

// ParseAndValidate is LoadAndValidate without the file read — exported
// so tests can feed YAML bytes directly without a temp file.
func ParseAndValidate(raw []byte, mode LoadMode) (Inventory, error) {
	var inv Inventory
	dec := yaml.NewDecoder(bytesReader(raw))
	if mode == ModeStrict {
		dec.KnownFields(true)
	}
	if err := dec.Decode(&inv); err != nil {
		// In strict mode, KnownFields surfaces a yaml error containing
		// "field <X> not found in type" — promote to ErrUnknownYAMLKey
		// so callers can branch on it.
		if mode == ModeStrict && containsAny(err.Error(), "not found in type", "field ") {
			return Inventory{}, fmt.Errorf("%w: %v", ErrUnknownYAMLKey, err)
		}
		return Inventory{}, fmt.Errorf("observability: yaml unmarshal: %w", err)
	}
	if inv.Version != 1 {
		return Inventory{}, fmt.Errorf("%w: %d (expected 1)", ErrUnsupportedVersion, inv.Version)
	}
	byName := make(map[string]Entry, len(inv.Metrics))
	for _, e := range inv.Metrics {
		if err := e.Validate(); err != nil {
			return Inventory{}, err
		}
		if _, dup := byName[e.Name]; dup {
			return Inventory{}, fmt.Errorf("%w: %q", ErrDuplicateMetricName, e.Name)
		}
		byName[e.Name] = e
	}
	return inv, nil
}

// Find returns the Entry by name (case-sensitive). Second return is
// false if not present.
func (inv Inventory) Find(name string) (Entry, bool) {
	for _, e := range inv.Metrics {
		if e.Name == name {
			return e, true
		}
	}
	return Entry{}, false
}

// AdmissionLookup builds an in-memory map<name → Entry> for O(1)
// runtime admission-control lookups. Snapshot the result at boot;
// inventory.yaml does not change at runtime.
func (inv Inventory) AdmissionLookup() map[string]Entry {
	m := make(map[string]Entry, len(inv.Metrics))
	for _, e := range inv.Metrics {
		m[e.Name] = e
	}
	return m
}
