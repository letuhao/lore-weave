package meta

import (
	"fmt"
	"os"
	"strings"

	"gopkg.in/yaml.v3"
)

// SensitivePath is one enumerated read path that triggers a meta_read_audit
// row. Loaded from meta-sensitive-read-paths.yml (Q-L1B-2).
type SensitivePath struct {
	ID          string   `yaml:"id"`
	Description string   `yaml:"description"`
	Tables      []string `yaml:"tables"`
	Rationale   string   `yaml:"rationale"`
	Reviewers   []string `yaml:"reviewers"`
}

// SensitivePathsFile is the on-disk YAML schema.
type SensitivePathsFile struct {
	Version int             `yaml:"version"`
	Paths   []SensitivePath `yaml:"paths"`
}

// SensitivePaths is the in-memory lookup struct. Immutable after Load.
type SensitivePaths struct {
	byID map[string]*SensitivePath
}

// LoadSensitivePaths parses meta-sensitive-read-paths.yml.
func LoadSensitivePaths(path string) (*SensitivePaths, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("meta: read sensitive paths %s: %w", path, err)
	}
	return ParseSensitivePaths(raw)
}

// ParseSensitivePaths parses an in-memory YAML payload.
func ParseSensitivePaths(raw []byte) (*SensitivePaths, error) {
	var f SensitivePathsFile
	if err := yaml.Unmarshal(raw, &f); err != nil {
		return nil, fmt.Errorf("meta: unmarshal sensitive paths: %w", err)
	}
	if f.Version != 1 {
		return nil, fmt.Errorf("meta: sensitive paths version=%d unsupported", f.Version)
	}
	if len(f.Paths) == 0 {
		return nil, fmt.Errorf("meta: sensitive paths file is empty")
	}
	sp := &SensitivePaths{byID: make(map[string]*SensitivePath, len(f.Paths))}
	for i := range f.Paths {
		p := f.Paths[i]
		if strings.TrimSpace(p.ID) == "" {
			return nil, fmt.Errorf("meta: sensitive path at index %d has empty id", i)
		}
		if _, dup := sp.byID[p.ID]; dup {
			return nil, fmt.Errorf("meta: duplicate sensitive path id %q", p.ID)
		}
		if len(p.Tables) == 0 {
			return nil, fmt.Errorf("meta: sensitive path %q has no tables", p.ID)
		}
		if len(p.Reviewers) == 0 {
			return nil, fmt.Errorf("meta: sensitive path %q has no reviewers (CODEOWNERS)", p.ID)
		}
		sp.byID[p.ID] = &p
	}
	return sp, nil
}

// Has reports whether the path id is registered. Read helpers call this to
// gate audit emission; CI lint uses it to detect bypass attempts.
func (sp *SensitivePaths) Has(id string) bool {
	if sp == nil {
		return false
	}
	_, ok := sp.byID[id]
	return ok
}

// Get returns the SensitivePath for an id (nil if unknown).
func (sp *SensitivePaths) Get(id string) *SensitivePath {
	if sp == nil {
		return nil
	}
	return sp.byID[id]
}

// IDs returns the list of registered ids (for test coverage / lint enumeration).
func (sp *SensitivePaths) IDs() []string {
	if sp == nil {
		return nil
	}
	out := make([]string, 0, len(sp.byID))
	for id := range sp.byID {
		out = append(out, id)
	}
	return out
}
