// Package framework implements the admin-cli command registry loader,
// dispatcher, and policy gates (impact_class, dry_run_required,
// double_approval_required).
//
// LOCKED Q-IDs honored (RAID cycle 36):
//   - Q-L7A-1: Loader auto-merges contracts/admin/registry/*.yaml.
//   - Q-L7A-2: Single binary; commands are dispatched by `<domain> <verb>`.
package framework

import (
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

// ImpactClass enumerates S5-D5 tier classifications.
type ImpactClass string

const (
	Tier1Destructive    ImpactClass = "tier-1-destructive"
	Tier2Griefing       ImpactClass = "tier-2-griefing"
	Tier3Informational  ImpactClass = "tier-3-informational"
)

// Param describes one parameter on a command.
type Param struct {
	Name        string
	Type        string
	Required    bool
	Description string
}

// Command is the in-memory shape of one registry entry.
type Command struct {
	Domain                  string
	Name                    string // full name including domain ("reality force-close")
	Verb                    string // sub-verb only ("force-close")
	Version                 string
	Summary                 string
	Handler                 string
	Params                  []Param
	ImpactClass             ImpactClass
	DryRunRequired          bool
	DoubleApprovalRequired  bool
	CarryForwardCycle       string
	LockedQsConsumed        []string
}

// Registry is the merged set of commands loaded from all per-domain YAML files.
type Registry struct {
	Domains  []string             // sorted domain names
	Commands map[string]*Command  // key = full Name
}

// ─────────────────────────────────────────────────────────────────────────────
// Loader (Q-L7A-1 per-domain auto-merge)
// ─────────────────────────────────────────────────────────────────────────────

// ErrRegistry signals a registry-loading failure.
var ErrRegistry = errors.New("admin-cli: registry")

// LoadRegistry walks the given directory, parses every *.yaml as a per-domain
// command list, and merges them. Domain collisions across files are rejected
// (Q-L7A-1 expects one file per domain).
func LoadRegistry(dir string) (*Registry, error) {
	reg := &Registry{Commands: map[string]*Command{}}
	domains := map[string]string{} // domain → first-seen file (collision detect)

	walkErr := filepath.WalkDir(dir, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		low := strings.ToLower(path)
		if !strings.HasSuffix(low, ".yaml") && !strings.HasSuffix(low, ".yml") {
			return nil
		}
		raw, rerr := os.ReadFile(path)
		if rerr != nil {
			return fmt.Errorf("%w: read %s: %v", ErrRegistry, path, rerr)
		}
		domain, cmds, perr := parseDomainFile(raw)
		if perr != nil {
			return fmt.Errorf("%w: parse %s: %v", ErrRegistry, path, perr)
		}
		if domain == "" {
			return fmt.Errorf("%w: %s: missing `domain:` key", ErrRegistry, path)
		}
		if prev, exists := domains[domain]; exists {
			return fmt.Errorf("%w: domain %q duplicated in %s and %s",
				ErrRegistry, domain, prev, path)
		}
		domains[domain] = path

		for _, c := range cmds {
			c.Domain = domain
			if !strings.HasPrefix(c.Name, domain+" ") && c.Name != domain {
				return fmt.Errorf("%w: %s: command %q must start with domain prefix %q",
					ErrRegistry, path, c.Name, domain)
			}
			c.Verb = strings.TrimPrefix(c.Name, domain+" ")
			if _, dup := reg.Commands[c.Name]; dup {
				return fmt.Errorf("%w: duplicate command %q", ErrRegistry, c.Name)
			}
			if !ValidImpactClass(c.ImpactClass) {
				return fmt.Errorf("%w: %s: command %q impact_class %q invalid",
					ErrRegistry, path, c.Name, c.ImpactClass)
			}
			// Tier-1 policy: dry_run + double_approval both required.
			if c.ImpactClass == Tier1Destructive {
				if !c.DryRunRequired {
					return fmt.Errorf("%w: %s: tier-1 command %q must have dry_run_required: true",
						ErrRegistry, path, c.Name)
				}
				if !c.DoubleApprovalRequired {
					return fmt.Errorf("%w: %s: tier-1 command %q must have double_approval_required: true",
						ErrRegistry, path, c.Name)
				}
			}
			reg.Commands[c.Name] = c
		}
		return nil
	})
	if walkErr != nil {
		return nil, walkErr
	}
	if len(reg.Commands) == 0 {
		return nil, fmt.Errorf("%w: no commands loaded from %s", ErrRegistry, dir)
	}
	for d := range domains {
		reg.Domains = append(reg.Domains, d)
	}
	sort.Strings(reg.Domains)
	return reg, nil
}

// ValidImpactClass returns true if ic is one of the three S5-D5 tiers.
func ValidImpactClass(ic ImpactClass) bool {
	switch ic {
	case Tier1Destructive, Tier2Griefing, Tier3Informational:
		return true
	}
	return false
}

// List returns commands sorted by Name (deterministic --help output).
func (r *Registry) List() []*Command {
	out := make([]*Command, 0, len(r.Commands))
	for _, c := range r.Commands {
		out = append(out, c)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Name < out[j].Name })
	return out
}

// ByDomain returns commands for a domain, sorted by Verb.
func (r *Registry) ByDomain(domain string) []*Command {
	var out []*Command
	for _, c := range r.Commands {
		if c.Domain == domain {
			out = append(out, c)
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Verb < out[j].Verb })
	return out
}
