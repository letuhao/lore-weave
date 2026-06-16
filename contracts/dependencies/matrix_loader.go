package dependencies

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

// LoadAndValidate reads + parses matrix.yaml and validates the full graph:
//
//  1. each Dependency.Validate() passes;
//  2. no duplicate dependency names;
//  3. every fallback name resolves to a known dep;
//  4. the fallback graph forms a DAG (no cycles).
//
// On any failure, the returned Matrix is the partially-loaded zero value
// — callers MUST refuse to start the service on error (a runtime call
// against an invalid matrix risks unbounded failover loops).
func LoadAndValidate(path string) (Matrix, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return Matrix{}, fmt.Errorf("dependencies: read matrix: %w", err)
	}
	return ParseAndValidate(raw)
}

// ParseAndValidate is LoadAndValidate without the file read — exported so
// tests can feed YAML bytes directly without a temp file.
func ParseAndValidate(raw []byte) (Matrix, error) {
	var m Matrix
	if err := yaml.Unmarshal(raw, &m); err != nil {
		return Matrix{}, fmt.Errorf("dependencies: yaml unmarshal: %w", err)
	}
	if m.Version != 1 {
		return Matrix{}, fmt.Errorf("dependencies: unsupported matrix version %d (expected 1)", m.Version)
	}
	// Per-entry validation + duplicate detection.
	byName := make(map[string]Dependency, len(m.Dependencies))
	for _, d := range m.Dependencies {
		if err := d.Validate(); err != nil {
			return Matrix{}, err
		}
		if _, dup := byName[d.Name]; dup {
			return Matrix{}, fmt.Errorf("%w: %q", ErrDuplicateDependency, d.Name)
		}
		byName[d.Name] = d
	}
	// Fallback reference resolution.
	for _, d := range m.Dependencies {
		for _, fb := range d.Fallback {
			if _, ok := byName[fb]; !ok {
				return Matrix{}, fmt.Errorf("%w: %q references unknown %q", ErrUnknownFallback, d.Name, fb)
			}
		}
	}
	// DAG (cycle) detection via DFS WHITE/GREY/BLACK coloring.
	if err := checkFallbackDAG(byName); err != nil {
		return Matrix{}, err
	}
	return m, nil
}

// Find returns the dep entry by name (case-sensitive). Second return is
// false if not present.
func (m Matrix) Find(name string) (Dependency, bool) {
	for _, d := range m.Dependencies {
		if d.Name == name {
			return d, true
		}
	}
	return Dependency{}, false
}

// checkFallbackDAG runs a 3-color DFS over the fallback graph and
// returns ErrFallbackCycle on detection. The error message includes
// the cycle path for postmortem.
//
// Algorithm:
//
//	WHITE  — never visited
//	GREY   — on the current DFS stack (back-edge to GREY = cycle)
//	BLACK  — fully explored
func checkFallbackDAG(byName map[string]Dependency) error {
	const (
		white = 0
		grey  = 1
		black = 2
	)
	color := make(map[string]int, len(byName))
	for n := range byName {
		color[n] = white
	}
	// path tracks the DFS stack so we can report the cycle.
	var path []string
	var dfs func(node string) error
	dfs = func(node string) error {
		color[node] = grey
		path = append(path, node)
		dep := byName[node]
		for _, fb := range dep.Fallback {
			switch color[fb] {
			case grey:
				// Found a cycle. Report from the first occurrence in path.
				cycleStart := 0
				for i, p := range path {
					if p == fb {
						cycleStart = i
						break
					}
				}
				cycle := append(append([]string{}, path[cycleStart:]...), fb)
				return fmt.Errorf("%w: %v", ErrFallbackCycle, cycle)
			case white:
				if err := dfs(fb); err != nil {
					return err
				}
			case black:
				// already fully explored; safe
			}
		}
		color[node] = black
		path = path[:len(path)-1]
		return nil
	}
	for n := range byName {
		if color[n] == white {
			if err := dfs(n); err != nil {
				return err
			}
		}
	}
	return nil
}
