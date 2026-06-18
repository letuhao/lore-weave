package events

import (
	"fmt"
	"io"
	"os"
	"sort"

	"gopkg.in/yaml.v3"
)

// Registry is the in-memory L2.F schema registry. Loaded from
// `_registry.yaml` at service startup; lookups are O(1) per (type, version).
//
// Fail-fast on parse error (L2.F acceptance): a malformed registry MUST
// cause service startup to abort, never to silently disable validation.
type Registry struct {
	entries map[string]*RegistryEntry           // by event_type
	byTV    map[entryKey]*RegistryEntry         // by (type, version)
	order   []string                            // stable iteration order
}

// RegistryEntry is one event_type's full descriptor.
type RegistryEntry struct {
	Name          string                `yaml:"name"`
	Aggregate     string                `yaml:"aggregate"`
	Versions      []uint32              `yaml:"versions"`
	ActiveVersion uint32                `yaml:"active_version"`
	GoStruct      string                `yaml:"go_struct"`
	Description   string                `yaml:"description"`
	ShippedCycle  int                   `yaml:"shipped_cycle"`
	Owner         string                `yaml:"owner"`
	Deprecations  []DeprecationEntry    `yaml:"deprecations,omitempty"`
}

// DeprecationEntry captures the R03 §12C.5 cooldown trio: deprecated_at,
// retire_after, upcaster_to. The eventgen tool uses upcaster_to to validate
// the upcaster chain is complete (no gaps).
type DeprecationEntry struct {
	Version       uint32 `yaml:"version"`
	DeprecatedAt  string `yaml:"deprecated_at"`
	RetireAfter   string `yaml:"retire_after"`
	UpcasterTo    uint32 `yaml:"upcaster_to"`
}

type entryKey struct {
	eventType string
	version   uint32
}

// Wire-shape (yaml file root).
type registryFile struct {
	Version uint32          `yaml:"version"`
	Events  []RegistryEntry `yaml:"events"`
}

// LoadRegistry loads the registry from `_registry.yaml` at `path`. It performs
// the L2.F structural validations:
//   - registry file format version is 1
//   - no duplicate event_type names
//   - every event has versions >= [1]
//   - active_version is in versions[]
//   - every deprecation entry's `version` is in versions[] AND
//     `upcaster_to` is in versions[]
//   - GoStruct is non-empty (eventgen needs it)
//   - Description non-empty (R03 §12C.7)
//
// Returns ErrRegistryParse on any violation.
func LoadRegistry(path string) (*Registry, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, ErrRegistryParse(fmt.Sprintf("open %s: %v", path, err))
	}
	defer f.Close()
	data, err := io.ReadAll(f)
	if err != nil {
		return nil, ErrRegistryParse(fmt.Sprintf("read %s: %v", path, err))
	}
	return ParseRegistry(data)
}

// ParseRegistry parses an in-memory registry YAML doc. Same semantics as
// LoadRegistry; broken out for tests + tooling (eventgen).
func ParseRegistry(data []byte) (*Registry, error) {
	var rf registryFile
	if err := yaml.Unmarshal(data, &rf); err != nil {
		return nil, ErrRegistryParse(fmt.Sprintf("yaml unmarshal: %v", err))
	}
	if rf.Version != 1 {
		return nil, ErrRegistryParse(fmt.Sprintf("unsupported registry file version %d (want 1)", rf.Version))
	}
	r := &Registry{
		entries: make(map[string]*RegistryEntry, len(rf.Events)),
		byTV:    make(map[entryKey]*RegistryEntry, len(rf.Events)*2),
		order:   make([]string, 0, len(rf.Events)),
	}
	for i := range rf.Events {
		e := rf.Events[i]
		if e.Name == "" {
			return nil, ErrRegistryParse(fmt.Sprintf("event index %d: empty name", i))
		}
		if _, dup := r.entries[e.Name]; dup {
			return nil, ErrRegistryParse(fmt.Sprintf("duplicate event_type %q", e.Name))
		}
		if e.Aggregate == "" {
			return nil, ErrRegistryParse(fmt.Sprintf("event %q: empty aggregate", e.Name))
		}
		if e.GoStruct == "" {
			return nil, ErrRegistryParse(fmt.Sprintf("event %q: empty go_struct", e.Name))
		}
		if e.Description == "" {
			return nil, ErrRegistryParse(fmt.Sprintf("event %q: empty description (R03 §12C.7)", e.Name))
		}
		if len(e.Versions) == 0 {
			return nil, ErrRegistryParse(fmt.Sprintf("event %q: empty versions", e.Name))
		}
		// versions must be strictly ascending and start at 1 or higher (1+ only — never v0)
		for j := 1; j < len(e.Versions); j++ {
			if e.Versions[j] <= e.Versions[j-1] {
				return nil, ErrRegistryParse(fmt.Sprintf("event %q: versions not strictly ascending", e.Name))
			}
		}
		if e.Versions[0] < 1 {
			return nil, ErrRegistryParse(fmt.Sprintf("event %q: first version %d < 1", e.Name, e.Versions[0]))
		}
		// active_version must be one of versions[]
		if !containsVer(e.Versions, e.ActiveVersion) {
			return nil, ErrRegistryParse(fmt.Sprintf("event %q: active_version %d not in versions %v", e.Name, e.ActiveVersion, e.Versions))
		}
		// deprecations
		for _, d := range e.Deprecations {
			if !containsVer(e.Versions, d.Version) {
				return nil, ErrRegistryParse(fmt.Sprintf("event %q: deprecation version %d not in versions %v", e.Name, d.Version, e.Versions))
			}
			if !containsVer(e.Versions, d.UpcasterTo) {
				return nil, ErrRegistryParse(fmt.Sprintf("event %q: deprecation upcaster_to %d not in versions %v", e.Name, d.UpcasterTo, e.Versions))
			}
			if d.UpcasterTo <= d.Version {
				return nil, ErrRegistryParse(fmt.Sprintf("event %q: deprecation upcaster_to %d must be > version %d (forward-only)", e.Name, d.UpcasterTo, d.Version))
			}
		}
		r.entries[e.Name] = &e
		r.order = append(r.order, e.Name)
		for _, v := range e.Versions {
			r.byTV[entryKey{e.Name, v}] = &e
		}
	}
	sort.Strings(r.order)
	return r, nil
}

// Lookup returns the registry entry for (event_type, event_version). Returns
// ErrUnknownEventSchema if the pair is not registered.
func (r *Registry) Lookup(eventType string, eventVersion uint32) (*RegistryEntry, error) {
	if e, ok := r.byTV[entryKey{eventType, eventVersion}]; ok {
		return e, nil
	}
	return nil, ErrUnknownEventSchema(eventType, eventVersion)
}

// LookupType returns the entry for an event_type (using its active_version).
// Returns ErrUnknownEventSchema if not registered.
func (r *Registry) LookupType(eventType string) (*RegistryEntry, error) {
	if e, ok := r.entries[eventType]; ok {
		return e, nil
	}
	return nil, ErrUnknownEventSchema(eventType, 0)
}

// EventTypes returns sorted event_type names (stable iteration for codegen).
func (r *Registry) EventTypes() []string {
	out := make([]string, len(r.order))
	copy(out, r.order)
	return out
}

// IsDeprecated reports whether (event_type, event_version) is on the
// deprecation list. Callers writing deprecated versions emit a warning per
// R03 §12C.5 — but the write is NOT rejected; only retirement is.
func (r *Registry) IsDeprecated(eventType string, eventVersion uint32) bool {
	e, ok := r.entries[eventType]
	if !ok {
		return false
	}
	for _, d := range e.Deprecations {
		if d.Version == eventVersion {
			return true
		}
	}
	return false
}

// Len returns the number of registered event_types.
func (r *Registry) Len() int { return len(r.entries) }

func containsVer(vs []uint32, v uint32) bool {
	for _, x := range vs {
		if x == v {
			return true
		}
	}
	return false
}
