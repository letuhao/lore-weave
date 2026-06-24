package meta

import (
	"fmt"
	"os"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

// TransitionGraph is the in-memory, validated representation of transitions.yaml.
// Loaded once at service startup; immutable thereafter (Q-L1B-3-adjacent).
type TransitionGraph struct {
	Resources map[string]*ResourceGraph
}

// ResourceGraph captures one resource's state machine.
type ResourceGraph struct {
	Name             string
	Table            string
	StateColumn      string
	States           map[string]struct{}
	InitialStates    map[string]struct{}
	TerminalStates   map[string]struct{}
	// transitions[from] = set of allowed to-states
	Transitions      map[string]map[string]struct{}
	// mutex[fromState] = set of forbidden to-states (overrides graph)
	MutualExclusions map[string]map[string]struct{}
}

// Allows reports whether (from → to) is a valid transition AND not forbidden
// by a mutual_exclusions rule.
func (r *ResourceGraph) Allows(from, to string) (allowed bool, forbiddenByMutex bool) {
	if to == from {
		// Self-loops not allowed by default (real state changes only).
		return false, false
	}
	tos, ok := r.Transitions[from]
	if !ok {
		return false, false
	}
	if _, in := tos[to]; !in {
		return false, false
	}
	if mx, ok := r.MutualExclusions[from]; ok {
		if _, forbidden := mx[to]; forbidden {
			return false, true
		}
	}
	return true, false
}

// --- YAML schema (parser types, kept private from public API) ----------------

type transitionRow struct {
	From string   `yaml:"from"`
	To   []string `yaml:"to"`
}
type mutexRow struct {
	IfStatus              string   `yaml:"if_status"`
	ForbiddenTransitions  []string `yaml:"forbidden_transitions"`
}
type resourceYAML struct {
	Table            string          `yaml:"table"`
	StateColumn      string          `yaml:"state_column"`
	States           []string        `yaml:"states"`
	InitialStates    []string        `yaml:"initial_states"`
	TerminalStates   []string        `yaml:"terminal_states"`
	Transitions      []transitionRow `yaml:"transitions"`
	MutualExclusions []mutexRow      `yaml:"mutual_exclusions"`
}
type transitionsFile struct {
	Version   int                       `yaml:"version"`
	Resources map[string]resourceYAML   `yaml:"resources"`
}

// LoadTransitions parses + validates a transitions.yaml file.
func LoadTransitions(path string) (*TransitionGraph, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("meta: read transitions %s: %w", path, err)
	}
	return ParseTransitions(raw)
}

// ParseTransitions parses + validates an in-memory YAML payload.
func ParseTransitions(raw []byte) (*TransitionGraph, error) {
	var f transitionsFile
	if err := yaml.Unmarshal(raw, &f); err != nil {
		return nil, fmt.Errorf("meta: unmarshal transitions: %w", err)
	}
	if f.Version != 1 {
		return nil, fmt.Errorf("%w: version=%d unsupported", ErrTransitionGraphInvalid, f.Version)
	}
	if len(f.Resources) == 0 {
		return nil, fmt.Errorf("%w: no resources defined", ErrTransitionGraphInvalid)
	}

	graph := &TransitionGraph{Resources: make(map[string]*ResourceGraph)}
	for name, r := range f.Resources {
		rg, err := buildResourceGraph(name, r)
		if err != nil {
			return nil, err
		}
		graph.Resources[name] = rg
	}
	return graph, nil
}

func buildResourceGraph(name string, r resourceYAML) (*ResourceGraph, error) {
	if strings.TrimSpace(r.Table) == "" {
		return nil, fmt.Errorf("%w: resource %s: empty table", ErrTransitionGraphInvalid, name)
	}
	if strings.TrimSpace(r.StateColumn) == "" {
		return nil, fmt.Errorf("%w: resource %s: empty state_column", ErrTransitionGraphInvalid, name)
	}
	if len(r.States) == 0 {
		return nil, fmt.Errorf("%w: resource %s: states list empty", ErrTransitionGraphInvalid, name)
	}
	rg := &ResourceGraph{
		Name:             name,
		Table:            r.Table,
		StateColumn:      r.StateColumn,
		States:           toSet(r.States),
		InitialStates:    toSet(r.InitialStates),
		TerminalStates:   toSet(r.TerminalStates),
		Transitions:      make(map[string]map[string]struct{}),
		MutualExclusions: make(map[string]map[string]struct{}),
	}

	// Duplicate state-name check
	if len(rg.States) != len(r.States) {
		return nil, fmt.Errorf("%w: resource %s: duplicate state name", ErrTransitionGraphInvalid, name)
	}

	// Initial / terminal state membership check
	for s := range rg.InitialStates {
		if _, ok := rg.States[s]; !ok {
			return nil, fmt.Errorf("%w: resource %s: initial state %q not in states", ErrTransitionGraphInvalid, name, s)
		}
	}
	for s := range rg.TerminalStates {
		if _, ok := rg.States[s]; !ok {
			return nil, fmt.Errorf("%w: resource %s: terminal state %q not in states", ErrTransitionGraphInvalid, name, s)
		}
	}
	if len(rg.InitialStates) == 0 {
		return nil, fmt.Errorf("%w: resource %s: no initial_states", ErrTransitionGraphInvalid, name)
	}

	// Build transition map; check from/to membership
	for _, tr := range r.Transitions {
		if _, ok := rg.States[tr.From]; !ok {
			return nil, fmt.Errorf("%w: resource %s: transition.from=%q not in states", ErrTransitionGraphInvalid, name, tr.From)
		}
		if len(tr.To) == 0 {
			return nil, fmt.Errorf("%w: resource %s: transition.from=%q has no to-states", ErrTransitionGraphInvalid, name, tr.From)
		}
		dst, ok := rg.Transitions[tr.From]
		if !ok {
			dst = make(map[string]struct{})
			rg.Transitions[tr.From] = dst
		}
		for _, to := range tr.To {
			if _, ok := rg.States[to]; !ok {
				return nil, fmt.Errorf("%w: resource %s: transition %s→%q not in states", ErrTransitionGraphInvalid, name, tr.From, to)
			}
			if to == tr.From {
				return nil, fmt.Errorf("%w: resource %s: self-loop %s→%s not allowed", ErrTransitionGraphInvalid, name, tr.From, to)
			}
			dst[to] = struct{}{}
		}
	}

	// Reachability: every non-initial state must be reachable from some initial state.
	reachable := bfsReach(rg.InitialStates, rg.Transitions)
	for s := range rg.States {
		if _, ok := rg.InitialStates[s]; ok {
			continue
		}
		if _, ok := reachable[s]; !ok {
			return nil, fmt.Errorf("%w: resource %s: state %q unreachable from initial_states", ErrTransitionGraphInvalid, name, s)
		}
	}

	// Non-terminal states must have at least one outgoing transition.
	for s := range rg.States {
		if _, isTerm := rg.TerminalStates[s]; isTerm {
			if _, hasOut := rg.Transitions[s]; hasOut {
				return nil, fmt.Errorf("%w: resource %s: terminal state %q has outgoing transitions", ErrTransitionGraphInvalid, name, s)
			}
			continue
		}
		if _, hasOut := rg.Transitions[s]; !hasOut {
			return nil, fmt.Errorf("%w: resource %s: non-terminal state %q has no outgoing transitions", ErrTransitionGraphInvalid, name, s)
		}
	}

	// Mutex rules
	for _, m := range r.MutualExclusions {
		if _, ok := rg.States[m.IfStatus]; !ok {
			return nil, fmt.Errorf("%w: resource %s: mutex.if_status=%q not in states", ErrTransitionGraphInvalid, name, m.IfStatus)
		}
		set, ok := rg.MutualExclusions[m.IfStatus]
		if !ok {
			set = make(map[string]struct{})
			rg.MutualExclusions[m.IfStatus] = set
		}
		for _, f := range m.ForbiddenTransitions {
			if _, ok := rg.States[f]; !ok {
				return nil, fmt.Errorf("%w: resource %s: mutex.forbidden=%q not in states", ErrTransitionGraphInvalid, name, f)
			}
			set[f] = struct{}{}
		}
	}
	return rg, nil
}

func toSet(xs []string) map[string]struct{} {
	out := make(map[string]struct{}, len(xs))
	for _, x := range xs {
		out[x] = struct{}{}
	}
	return out
}

func bfsReach(seeds map[string]struct{}, edges map[string]map[string]struct{}) map[string]struct{} {
	out := make(map[string]struct{})
	queue := make([]string, 0, len(seeds))
	for s := range seeds {
		out[s] = struct{}{}
		queue = append(queue, s)
	}
	for len(queue) > 0 {
		head := queue[0]
		queue = queue[1:]
		for next := range edges[head] {
			if _, seen := out[next]; seen {
				continue
			}
			out[next] = struct{}{}
			queue = append(queue, next)
		}
	}
	return out
}

// ResourceNames returns the resources defined in this graph (sorted, for stable test output).
func (g *TransitionGraph) ResourceNames() []string {
	out := make([]string, 0, len(g.Resources))
	for n := range g.Resources {
		out = append(out, n)
	}
	sort.Strings(out)
	return out
}
