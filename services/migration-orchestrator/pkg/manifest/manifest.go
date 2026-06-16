// Package manifest loads contracts/migrations/manifest.yaml.
//
// The manifest is the ordered, declarative list of every schema migration
// the orchestrator may apply to a per-reality DB. Each entry carries:
//   - id           — stable identifier matching the SQL filename stem
//     (e.g. "0001_initial" matches contracts/migrations/per_reality/0001_initial.up.sql)
//   - version      — monotonically-increasing version number
//   - breaking     — if true, route through the canary module (1 reality
//     first; verify; then fan out)
//   - dependencies — list of prior migration IDs that must be applied
//
// Cycle 6 (L1.D.5) ships the loader + the FIRST entry referencing the
// cycle-5 per-reality skeleton (0001_initial). Cycle 8+ will add L2 entries.
package manifest

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"

	"gopkg.in/yaml.v3"
)

// Migration is one declared migration entry.
type Migration struct {
	ID           string   `yaml:"id"`
	Version      uint32   `yaml:"version"`
	Breaking     bool     `yaml:"breaking"`
	Dependencies []string `yaml:"dependencies"`
	Description  string   `yaml:"description"`
}

// Manifest is the parsed YAML.
type Manifest struct {
	Version    uint32      `yaml:"version"`
	Migrations []Migration `yaml:"migrations"`
}

// ErrManifestInvalid signals a manifest that failed validation.
var ErrManifestInvalid = errors.New("manifest invalid")

// Load reads + validates the manifest at path.
func Load(path string) (*Manifest, error) {
	clean := filepath.Clean(path)
	raw, err := os.ReadFile(clean)
	if err != nil {
		return nil, fmt.Errorf("manifest: read %s: %w", clean, err)
	}
	return Parse(raw)
}

// Parse validates + returns a Manifest from raw YAML.
func Parse(raw []byte) (*Manifest, error) {
	var m Manifest
	if err := yaml.Unmarshal(raw, &m); err != nil {
		return nil, fmt.Errorf("manifest: unmarshal: %w", err)
	}
	if err := m.Validate(); err != nil {
		return nil, err
	}
	return &m, nil
}

// Validate enforces structural invariants:
//   - version must be 1 (current schema)
//   - migrations must be non-empty
//   - no duplicate id
//   - versions monotonically increasing AND start at 1
//   - every dependency must reference an earlier id in the list
//   - the first migration MUST be "0001_initial" (cycle 5 carry-forward
//     invariant: per-reality DBs always boot with the skeleton)
func (m *Manifest) Validate() error {
	if m.Version != 1 {
		return fmt.Errorf("%w: version=%d (expected 1)", ErrManifestInvalid, m.Version)
	}
	if len(m.Migrations) == 0 {
		return fmt.Errorf("%w: empty migrations list", ErrManifestInvalid)
	}
	if m.Migrations[0].ID != "0001_initial" {
		return fmt.Errorf("%w: first migration must be 0001_initial (cycle 5 per-reality skeleton); got %q",
			ErrManifestInvalid, m.Migrations[0].ID)
	}
	seen := make(map[string]uint32, len(m.Migrations))
	var prevVer uint32
	for i, mig := range m.Migrations {
		if mig.ID == "" {
			return fmt.Errorf("%w: migrations[%d].id empty", ErrManifestInvalid, i)
		}
		if _, dup := seen[mig.ID]; dup {
			return fmt.Errorf("%w: migrations[%d].id %q duplicate", ErrManifestInvalid, i, mig.ID)
		}
		if mig.Version == 0 {
			return fmt.Errorf("%w: migrations[%d].version=0 (must be ≥ 1)", ErrManifestInvalid, i)
		}
		if i > 0 && mig.Version <= prevVer {
			return fmt.Errorf("%w: migrations[%d].version=%d not > prev=%d (monotonic required)",
				ErrManifestInvalid, i, mig.Version, prevVer)
		}
		if i == 0 && mig.Version != 1 {
			return fmt.Errorf("%w: migrations[0].version=%d (must start at 1)", ErrManifestInvalid, mig.Version)
		}
		for _, dep := range mig.Dependencies {
			if _, ok := seen[dep]; !ok {
				return fmt.Errorf("%w: migrations[%d].dependencies references %q before its declaration",
					ErrManifestInvalid, i, dep)
			}
		}
		seen[mig.ID] = mig.Version
		prevVer = mig.Version
	}
	return nil
}

// Find returns the migration with the given id (nil if not found).
func (m *Manifest) Find(id string) *Migration {
	for i := range m.Migrations {
		if m.Migrations[i].ID == id {
			return &m.Migrations[i]
		}
	}
	return nil
}
