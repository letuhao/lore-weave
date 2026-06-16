package prompt

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// TemplateRegistry is the parsed shape of templates/registry.yaml.
// Cycle 31 L6.K.5 keeps the parser intentionally light — the
// LLM-logic sub-program may replace this with a yaml.v3 client when
// it lands the real templates; foundation V1 reads the file with a
// minimal hand-rolled parser to avoid pulling yaml as a foundation
// dep.
type TemplateRegistry struct {
	// Intents maps Intent → active version (and deprecated list).
	Intents map[Intent]TemplateRegistryEntry
}

// TemplateRegistryEntry holds the per-intent active + deprecated
// version list.
type TemplateRegistryEntry struct {
	ActiveVersion      int
	DeprecatedVersions []int
	Status             string // "skeleton" | "active" (per Q-L6K-1)
}

// ErrTemplateRegistryMissing is returned when registry.yaml is absent
// or malformed.
var ErrTemplateRegistryMissing = errors.New("template_loader: registry.yaml missing or malformed")

// LoadTemplateRegistry reads templates/registry.yaml from the given
// root (typically contracts/prompt/templates). Returns a parsed
// TemplateRegistry or an error.
//
// **Failure modes (all FAIL per Q-L6H-1):**
//   - registry.yaml not found.
//   - Any intent in AllIntents() missing from the file.
//   - Active version's tmpl/meta files missing on disk.
func LoadTemplateRegistry(rootDir string) (TemplateRegistry, error) {
	path := filepath.Join(rootDir, "registry.yaml")
	data, err := os.ReadFile(path)
	if err != nil {
		return TemplateRegistry{}, fmt.Errorf("%w: %v", ErrTemplateRegistryMissing, err)
	}

	reg := TemplateRegistry{Intents: make(map[Intent]TemplateRegistryEntry)}
	if err := parseRegistry(string(data), &reg); err != nil {
		return TemplateRegistry{}, fmt.Errorf("%w: %v", ErrTemplateRegistryMissing, err)
	}

	// Verify every Intent has an entry.
	for _, it := range AllIntents() {
		entry, ok := reg.Intents[it]
		if !ok {
			return TemplateRegistry{}, fmt.Errorf("%w: intent %q missing from registry.yaml", ErrTemplateRegistryMissing, it)
		}
		// Verify the active-version tmpl + meta are on disk.
		intentDir := filepath.Join(rootDir, string(it))
		tmpl := filepath.Join(intentDir, fmt.Sprintf("v%d.tmpl", entry.ActiveVersion))
		meta := filepath.Join(intentDir, fmt.Sprintf("v%d.meta.yaml", entry.ActiveVersion))
		if _, err := os.Stat(tmpl); err != nil {
			return TemplateRegistry{}, fmt.Errorf("%w: %s missing", ErrTemplateRegistryMissing, tmpl)
		}
		if _, err := os.Stat(meta); err != nil {
			return TemplateRegistry{}, fmt.Errorf("%w: %s missing", ErrTemplateRegistryMissing, meta)
		}
	}

	return reg, nil
}

// parseRegistry implements a minimal YAML-subset parser for the
// registry.yaml shape. We deliberately avoid pulling yaml.v3 as a
// foundation dep — the file is governance-controlled + simple, and a
// hand-rolled parser keeps the foundation build surface small.
//
// Accepted shape:
//
//	intents:
//	  session_turn:
//	    active_version: 1
//	    deprecated_versions: []
//	    status: skeleton
//
// Unknown keys are tolerated (forward compat); unknown intents are
// stored but ignored by callers (only AllIntents() must be present).
func parseRegistry(src string, reg *TemplateRegistry) error {
	lines := strings.Split(src, "\n")
	var currentIntent Intent
	var inIntents bool
	for ln, raw := range lines {
		s := stripComment(raw)
		if strings.TrimSpace(s) == "" {
			continue
		}
		// Top-level "intents:" key.
		if strings.HasPrefix(s, "intents:") {
			inIntents = true
			continue
		}
		if !inIntents {
			continue
		}
		// Intent-level entry (2 leading spaces): "  session_turn:"
		if strings.HasPrefix(s, "  ") && !strings.HasPrefix(s, "    ") && strings.HasSuffix(strings.TrimSpace(s), ":") {
			name := strings.TrimSpace(strings.TrimSuffix(strings.TrimSpace(s), ":"))
			currentIntent = Intent(name)
			reg.Intents[currentIntent] = TemplateRegistryEntry{}
			continue
		}
		// Per-intent fields (4 leading spaces): "    active_version: 1"
		if strings.HasPrefix(s, "    ") && currentIntent != "" {
			kv := strings.TrimSpace(s)
			parts := strings.SplitN(kv, ":", 2)
			if len(parts) != 2 {
				return fmt.Errorf("line %d: malformed key/value: %q", ln+1, kv)
			}
			key := strings.TrimSpace(parts[0])
			val := strings.TrimSpace(parts[1])
			entry := reg.Intents[currentIntent]
			switch key {
			case "active_version":
				var n int
				if _, err := fmt.Sscanf(val, "%d", &n); err != nil {
					return fmt.Errorf("line %d: active_version not int: %q", ln+1, val)
				}
				entry.ActiveVersion = n
			case "status":
				entry.Status = val
			case "deprecated_versions":
				// Accept "[]" or "[1, 2]" — minimal parser.
				val = strings.TrimSpace(val)
				val = strings.TrimPrefix(val, "[")
				val = strings.TrimSuffix(val, "]")
				if val == "" {
					entry.DeprecatedVersions = nil
				} else {
					for _, p := range strings.Split(val, ",") {
						p = strings.TrimSpace(p)
						var n int
						if _, err := fmt.Sscanf(p, "%d", &n); err != nil {
							return fmt.Errorf("line %d: deprecated_versions item not int: %q", ln+1, p)
						}
						entry.DeprecatedVersions = append(entry.DeprecatedVersions, n)
					}
				}
			}
			reg.Intents[currentIntent] = entry
		}
	}
	return nil
}

func stripComment(s string) string {
	if i := strings.Index(s, "#"); i >= 0 {
		return s[:i]
	}
	return s
}
