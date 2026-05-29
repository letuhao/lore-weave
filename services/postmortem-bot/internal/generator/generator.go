// Package generator implements L7.D.9 — postmortem stub generation.
//
// On IncidentClosedV1 the bot creates docs/sre/postmortems/<id>.md from
// docs/sre/postmortems/TEMPLATE.md, substituting the fields it can fill
// automatically (id, severity, title, declared/resolved times, duration).
// SEV0/SEV1 always get a postmortem (postmortem_due); for lower severities
// the bot honors the event's PostmortemDue flag.
//
// The generator is pure (string in → string out + path), so unit tests do
// not need a filesystem. WriteStub does the single side effect (file write)
// and refuses to clobber an existing postmortem.
package generator

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/loreweave/foundation/contracts/incidents"
	"gopkg.in/yaml.v3"
)

// RootCauseEnum holds the loaded 12-enum taxonomy for validation.
type RootCauseEnum struct {
	ids map[string]bool
}

type rootCauseFile struct {
	Version          int `yaml:"version"`
	ExpectedEnumCount int `yaml:"expected_enum_count"`
	RootCauses       []struct {
		ID string `yaml:"id"`
	} `yaml:"root_causes"`
}

// Render fills the template body for a closed incident. It does NOT touch
// the filesystem; callers pass the template contents in.
func Render(templateBody string, ev incidents.IncidentClosedV1) (string, error) {
	if err := ev.Validate(); err != nil {
		return "", fmt.Errorf("generator: invalid closed event: %w", err)
	}
	dur := ev.ResolvedAt.Sub(ev.DeclaredAt)
	repl := map[string]string{
		"{{INCIDENT_ID}}": ev.IncidentID,
		"{{SEVERITY}}":    string(ev.Severity),
		"{{TITLE}}":       ev.Title,
		"{{DECLARED_AT}}": fmtTime(ev.DeclaredAt),
		"{{RESOLVED_AT}}": fmtTime(ev.ResolvedAt),
		"{{DURATION}}":    dur.String(),
		"{{IC}}":          "", // filled by IC during review
	}
	out := templateBody
	for k, v := range repl {
		out = strings.ReplaceAll(out, k, v)
	}
	return out, nil
}

func fmtTime(t time.Time) string {
	if t.IsZero() {
		return ""
	}
	return t.UTC().Format(time.RFC3339)
}

// StubPath returns the canonical postmortem path for an incident id, rooted
// at dir (typically "docs/sre/postmortems").
func StubPath(dir, incidentID string) string {
	safe := strings.ReplaceAll(incidentID, "/", "-")
	return filepath.Join(dir, safe+".md")
}

// WriteStub renders + writes the postmortem stub. Refuses to overwrite an
// existing file (idempotent close re-delivery must not clobber edits).
func WriteStub(templatePath, outDir string, ev incidents.IncidentClosedV1) (string, error) {
	tmpl, err := os.ReadFile(templatePath)
	if err != nil {
		return "", fmt.Errorf("generator: read template %s: %w", templatePath, err)
	}
	rendered, err := Render(string(tmpl), ev)
	if err != nil {
		return "", err
	}
	out := StubPath(outDir, ev.IncidentID)
	if _, err := os.Stat(out); err == nil {
		return out, fmt.Errorf("generator: postmortem already exists, refusing to clobber: %s", out)
	}
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return "", fmt.Errorf("generator: mkdir %s: %w", outDir, err)
	}
	if err := os.WriteFile(out, []byte(rendered), 0o644); err != nil {
		return "", fmt.Errorf("generator: write %s: %w", out, err)
	}
	return out, nil
}

// LoadRootCauseEnum loads + validates the 12-enum taxonomy.
func LoadRootCauseEnum(path string) (*RootCauseEnum, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("generator: read root_cause_enum %s: %w", path, err)
	}
	var f rootCauseFile
	if err := yaml.Unmarshal(raw, &f); err != nil {
		return nil, fmt.Errorf("generator: parse root_cause_enum: %w", err)
	}
	if f.ExpectedEnumCount > 0 && len(f.RootCauses) != f.ExpectedEnumCount {
		return nil, fmt.Errorf("generator: root_cause_enum drift — expected %d got %d", f.ExpectedEnumCount, len(f.RootCauses))
	}
	e := &RootCauseEnum{ids: make(map[string]bool, len(f.RootCauses))}
	for _, rc := range f.RootCauses {
		if rc.ID == "" {
			return nil, errors.New("generator: root_cause_enum has empty id")
		}
		e.ids[rc.ID] = true
	}
	if len(e.ids) == 0 {
		return nil, errors.New("generator: root_cause_enum empty")
	}
	return e, nil
}

// IsValidRootCause reports whether id is a declared root-cause class.
func (e *RootCauseEnum) IsValidRootCause(id string) bool {
	return e.ids[id]
}

// Count returns the number of root-cause classes loaded.
func (e *RootCauseEnum) Count() int { return len(e.ids) }
