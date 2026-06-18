// Package catalog loads the declarative conformance case definitions.
//
// A case is one YAML file under the catalog tree (catalog/generic/,
// catalog/<service>/). Declarative YAML — not Go-registered cases — keeps case
// authorship open to non-Go contributors and keeps the runner generic
// (plan §2.1–2.2).
//
// The reserved filename `expunge.yaml` is NOT a case; it is the known-failures
// list, loaded separately by package expunge (xfstests `-E` semantics). Load
// skips it.
package catalog

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

// ExpungeFilename is the reserved basename of the known-failures list. It lives
// in the catalog tree but is never parsed as a case.
const ExpungeFilename = "expunge.yaml"

// Kind is the execution shape of a case. The runner maps each kind's outcome to
// a verdict; the kind also documents what infra the case typically needs.
type Kind string

const (
	KindLint      Kind = "lint"       // a shell lint: exit 0/1/2
	KindGoTest    Kind = "go-test"    // `go test`, usually `-tags=integration`
	KindRustTest  Kind = "rust-test"  // `cargo test`
	KindLiveProbe Kind = "live-probe" // a live-smoke against a running stack
)

func (k Kind) valid() bool {
	switch k {
	case KindLint, KindGoTest, KindRustTest, KindLiveProbe:
		return true
	default:
		return false
	}
}

// Case is one conformance assertion, parsed from a single YAML file.
type Case struct {
	ID          string `yaml:"id"`
	Description string `yaml:"description"`
	Invariant   string `yaml:"invariant"` // optional I-/PRR-ref for traceability

	Kind    Kind     `yaml:"kind"`
	Command []string `yaml:"command"` // argv; executed from the repo root

	// Requires names preconditions the runner must satisfy before executing
	// (e.g. "docker", "database_url"). An unmet requirement → notrun.
	Requires []string `yaml:"requires"`
	// SkipWhen names stack predicates that make the case not-applicable
	// (e.g. "single-superuser", "no-provisioner"). A matched predicate → skip.
	SkipWhen []string `yaml:"skip_when"`

	// FailClosedOnSetupError promotes a harness/setup error (exit ≥2) from the
	// default notrun to fail. Use for cases where a setup error hides a real
	// regression rather than a missing tool.
	FailClosedOnSetupError bool `yaml:"fail_closed_on_setup_error"`

	// path is the source file, for error messages. Not serialized.
	path string `yaml:"-"`
}

// Path returns the source file the case was loaded from.
func (c Case) Path() string { return c.path }

func (c Case) validate() error {
	if strings.TrimSpace(c.ID) == "" {
		return fmt.Errorf("missing id")
	}
	if !c.Kind.valid() {
		return fmt.Errorf("case %q: invalid kind %q (want lint|go-test|rust-test|live-probe)", c.ID, c.Kind)
	}
	if len(c.Command) == 0 {
		return fmt.Errorf("case %q: empty command", c.ID)
	}
	return nil
}

// Load walks the catalog root recursively, parsing every *.yaml / *.yml file
// (except the reserved expunge.yaml) into a Case. It validates each case and
// enforces globally-unique ids. Cases are returned sorted by id for
// deterministic run order.
func Load(root string) ([]Case, error) {
	var cases []Case
	seen := map[string]string{} // id -> source path, for dup detection

	err := filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		ext := strings.ToLower(filepath.Ext(path))
		if ext != ".yaml" && ext != ".yml" {
			return nil
		}
		if filepath.Base(path) == ExpungeFilename {
			return nil // the known-failures list, not a case
		}

		raw, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		var c Case
		dec := yaml.NewDecoder(strings.NewReader(string(raw)))
		dec.KnownFields(true) // reject unknown keys → typos surface loudly
		if err := dec.Decode(&c); err != nil {
			return fmt.Errorf("%s: %w", path, err)
		}
		c.path = path
		if err := c.validate(); err != nil {
			return fmt.Errorf("%s: %w", path, err)
		}
		if prev, dup := seen[c.ID]; dup {
			return fmt.Errorf("duplicate case id %q in %s and %s", c.ID, prev, path)
		}
		seen[c.ID] = path
		cases = append(cases, c)
		return nil
	})
	if err != nil {
		return nil, err
	}

	sort.Slice(cases, func(i, j int) bool { return cases[i].ID < cases[j].ID })
	return cases, nil
}
