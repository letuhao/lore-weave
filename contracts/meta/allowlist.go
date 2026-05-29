package meta

import (
	"fmt"
	"os"
	"strings"

	"gopkg.in/yaml.v3"
)

// Allowlist is the set of meta tables the library accepts writes to.
// Defense-in-depth so a service can't accidentally write to a table its
// design didn't anticipate.
//
// Loaded from `events_allowlist.yaml` (Q-L1B-1): the same file also lists
// which (table, op) pairs emit an outbox event.
type Allowlist interface {
	AllowsTable(table string) bool
	EmitsEvent(table string, op MetaWriteOp) (eventName string, ok bool)
	Tables() []string
}

// EventBinding maps a (table, operation) tuple to the outbox event name
// the library appends after a successful write (in same TX).
type EventBinding struct {
	Op       MetaWriteOp `yaml:"op"`
	EventName string     `yaml:"event_name"`
}

// AllowlistEntry is one table's record in events_allowlist.yaml.
type AllowlistEntry struct {
	Table  string         `yaml:"table"`
	Events []EventBinding `yaml:"events"`
	// Owner is informational — service that owns writes to this table
	// (matches the L1.A "Written by" column).
	Owner string `yaml:"owner"`
	// Notes is informational — reference to the L1.A section that
	// authoritatively defines this table.
	Notes string `yaml:"notes"`
}

// AllowlistFile is the on-disk YAML schema.
type AllowlistFile struct {
	Version int              `yaml:"version"`
	Entries []AllowlistEntry `yaml:"entries"`
}

type allowlistImpl struct {
	tables map[string]struct{}
	events map[string]map[MetaWriteOp]string // table → op → event_name
}

// AllowsTable returns true if the table is in the allowlist.
func (a *allowlistImpl) AllowsTable(table string) bool {
	_, ok := a.tables[table]
	return ok
}

// EmitsEvent returns the outbox event name for (table, op) if registered.
func (a *allowlistImpl) EmitsEvent(table string, op MetaWriteOp) (string, bool) {
	ops, ok := a.events[table]
	if !ok {
		return "", false
	}
	name, ok := ops[op]
	return name, ok
}

// Tables returns the sorted-ish (insertion-order) list of allowed tables;
// used by tests + CI lint to spot-check coverage vs L1.A.
func (a *allowlistImpl) Tables() []string {
	out := make([]string, 0, len(a.tables))
	for t := range a.tables {
		out = append(out, t)
	}
	return out
}

// LoadAllowlist parses an events_allowlist.yaml file. Fails fast on any
// duplicate table, unknown op, or empty table name (Q-L1B-1 hygiene).
func LoadAllowlist(path string) (Allowlist, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("meta: read allowlist %s: %w", path, err)
	}
	return ParseAllowlist(raw)
}

// ParseAllowlist parses an in-memory YAML payload. Same rules as LoadAllowlist.
func ParseAllowlist(raw []byte) (Allowlist, error) {
	var f AllowlistFile
	if err := yaml.Unmarshal(raw, &f); err != nil {
		return nil, fmt.Errorf("meta: unmarshal allowlist: %w", err)
	}
	if f.Version != 1 {
		return nil, fmt.Errorf("meta: allowlist version=%d unsupported (want 1)", f.Version)
	}
	impl := &allowlistImpl{
		tables: make(map[string]struct{}),
		events: make(map[string]map[MetaWriteOp]string),
	}
	for _, e := range f.Entries {
		tbl := strings.TrimSpace(e.Table)
		if tbl == "" {
			return nil, fmt.Errorf("meta: allowlist entry has empty table")
		}
		if _, dup := impl.tables[tbl]; dup {
			return nil, fmt.Errorf("meta: allowlist duplicate table %q", tbl)
		}
		impl.tables[tbl] = struct{}{}
		if len(e.Events) == 0 {
			continue
		}
		ops := make(map[MetaWriteOp]string)
		for _, b := range e.Events {
			if !b.Op.IsValid() {
				return nil, fmt.Errorf("meta: allowlist %s event op=%q invalid", tbl, b.Op)
			}
			if strings.TrimSpace(b.EventName) == "" {
				return nil, fmt.Errorf("meta: allowlist %s op=%s missing event_name", tbl, b.Op)
			}
			if _, dup := ops[b.Op]; dup {
				return nil, fmt.Errorf("meta: allowlist %s op=%s duplicated", tbl, b.Op)
			}
			ops[b.Op] = b.EventName
		}
		impl.events[tbl] = ops
	}
	return impl, nil
}
