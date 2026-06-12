package capacity

import (
	"bytes"
	"fmt"
	"os"
	"strings"
	"sync"
	"sync/atomic"

	"gopkg.in/yaml.v3"
)

// LoadMode mirrors observability.LoadMode — strict rejects unknown
// YAML keys; lax accepts them (forward-compat).
type LoadMode int

const (
	ModeStrict LoadMode = iota
	ModeLax
)

// LoadAndValidate reads + parses budgets.yaml and validates:
//
//  1. version supported (== 1)
//  2. each Service.Validate() passes
//  3. no duplicate service names
//  4. (strict mode) no unknown YAML keys
func LoadAndValidate(path string, mode LoadMode) (Budgets, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return Budgets{}, fmt.Errorf("capacity: read budgets: %w", err)
	}
	return ParseAndValidate(raw, mode)
}

// ParseAndValidate is LoadAndValidate without the file read.
func ParseAndValidate(raw []byte, mode LoadMode) (Budgets, error) {
	var b Budgets
	dec := yaml.NewDecoder(bytes.NewReader(raw))
	if mode == ModeStrict {
		dec.KnownFields(true)
	}
	if err := dec.Decode(&b); err != nil {
		if mode == ModeStrict && (strings.Contains(err.Error(), "not found in type") || strings.Contains(err.Error(), "field ")) {
			return Budgets{}, fmt.Errorf("%w: %v", ErrUnknownYAMLKey, err)
		}
		return Budgets{}, fmt.Errorf("capacity: yaml unmarshal: %w", err)
	}
	if b.Version != 1 {
		return Budgets{}, fmt.Errorf("%w: %d (expected 1)", ErrUnsupportedVersion, b.Version)
	}
	seen := make(map[string]struct{}, len(b.Services))
	for _, s := range b.Services {
		if err := s.Validate(); err != nil {
			return Budgets{}, err
		}
		if _, dup := seen[s.Name]; dup {
			return Budgets{}, fmt.Errorf("%w: %q", ErrDuplicateService, s.Name)
		}
		seen[s.Name] = struct{}{}
	}
	return b, nil
}

// Find returns the Service entry by name (case-sensitive).
func (b Budgets) Find(name string) (Service, bool) {
	for _, s := range b.Services {
		if s.Name == name {
			return s, true
		}
	}
	return Service{}, false
}

// Names returns all declared service names (deterministic order:
// matches YAML order).
func (b Budgets) Names() []string {
	out := make([]string, 0, len(b.Services))
	for _, s := range b.Services {
		out = append(out, s.Name)
	}
	return out
}

// ─────────────────────────────────────────────────────────────────────
// Admission — runtime gate called by deploy pipelines
// ─────────────────────────────────────────────────────────────────────

// Admission is the runtime admission surface for capacity. Construct
// once at deploy-pipeline boot; query RegisterService(name) before
// generating HPA/KEDA manifests for that service.
type Admission struct {
	lookup     map[string]Service
	registered sync.Map // name → struct{}
	checks     atomic.Uint64
	rejections atomic.Uint64
}

// NewAdmission wraps the loaded budgets. budgets MUST already be
// validated (LoadAndValidate). The lookup is snapshot at construction
// time.
func NewAdmission(b Budgets) *Admission {
	a := &Admission{lookup: make(map[string]Service, len(b.Services))}
	for _, s := range b.Services {
		a.lookup[s.Name] = s
	}
	return a
}

// RegisterService confirms that the requested service has a capacity
// entry. Returns ErrUnregisteredService if missing. Successful calls
// are idempotent.
func (a *Admission) RegisterService(name string) (Service, error) {
	a.checks.Add(1)
	s, ok := a.lookup[name]
	if !ok {
		a.rejections.Add(1)
		return Service{}, fmt.Errorf("%w: %q", ErrUnregisteredService, name)
	}
	a.registered.Store(name, struct{}{})
	return s, nil
}

// IsRegistered returns true if the named service is in the budgets
// AND RegisterService(name) was previously called.
func (a *Admission) IsRegistered(name string) bool {
	_, ok := a.registered.Load(name)
	return ok
}

// RemainingBudget returns the unused capacity headroom for a service
// at the given tier. Headroom = max - currentReplicas. Useful for
// admission-of-scale-up requests.
//
// Returns (-1, ErrUnregisteredService) if the service is unknown.
func (a *Admission) RemainingBudget(name string, tier string, currentReplicas int) (int, error) {
	s, ok := a.lookup[name]
	if !ok {
		return -1, fmt.Errorf("%w: %q", ErrUnregisteredService, name)
	}
	var maxR int
	switch tier {
	case "v1":
		maxR = s.V1.MaxReplicas
	case "v3":
		maxR = s.V3.MaxReplicas
	default:
		return -1, fmt.Errorf("%w: name=%q unknown tier %q", ErrInvalidService, name, tier)
	}
	headroom := maxR - currentReplicas
	if headroom < 0 {
		headroom = 0
	}
	return headroom, nil
}

// Stats returns (checks, rejections).
func (a *Admission) Stats() (uint64, uint64) {
	return a.checks.Load(), a.rejections.Load()
}
