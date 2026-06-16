package generator

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/loreweave/foundation/contracts/incidents"
)

func closedEvent() incidents.IncidentClosedV1 {
	declared := time.Unix(1700000000, 0).UTC()
	return incidents.IncidentClosedV1{
		Type:          incidents.TypeIncidentClosedV1,
		IncidentID:    "INC-2026-0531-0001",
		Severity:      incidents.SEV0,
		Title:         "DB primary down",
		DeclaredAt:    declared,
		ResolvedAt:    declared.Add(90 * time.Minute),
		UserVisible:   true,
		PostmortemDue: true,
	}
}

func repoRoot(t *testing.T) string {
	t.Helper()
	return filepath.Join("..", "..", "..", "..")
}

func TestRender(t *testing.T) {
	tmplPath := filepath.Join(repoRoot(t), "docs", "sre", "postmortems", "TEMPLATE.md")
	tmpl, err := os.ReadFile(tmplPath)
	if err != nil {
		t.Fatalf("read template: %v", err)
	}
	out, err := Render(string(tmpl), closedEvent())
	if err != nil {
		t.Fatalf("Render: %v", err)
	}
	if !strings.Contains(out, "INC-2026-0531-0001") {
		t.Error("rendered postmortem missing incident id")
	}
	if !strings.Contains(out, "SEV0") {
		t.Error("rendered postmortem missing severity")
	}
	if strings.Contains(out, "{{INCIDENT_ID}}") {
		t.Error("unresolved placeholder remains")
	}
	if !strings.Contains(out, "1h30m0s") {
		t.Errorf("duration not rendered correctly: missing 1h30m0s")
	}
}

func TestRender_InvalidEvent(t *testing.T) {
	if _, err := Render("body", incidents.IncidentClosedV1{}); err == nil {
		t.Error("invalid event must error")
	}
}

func TestStubPath(t *testing.T) {
	if got := StubPath("docs/sre/postmortems", "INC-1"); got != filepath.Join("docs/sre/postmortems", "INC-1.md") {
		t.Errorf("StubPath = %q", got)
	}
}

func TestWriteStub_AndNoClobber(t *testing.T) {
	tmplPath := filepath.Join(repoRoot(t), "docs", "sre", "postmortems", "TEMPLATE.md")
	outDir := t.TempDir()
	p, err := WriteStub(tmplPath, outDir, closedEvent())
	if err != nil {
		t.Fatalf("WriteStub: %v", err)
	}
	if _, err := os.Stat(p); err != nil {
		t.Fatalf("stub not written: %v", err)
	}
	// Second call must refuse to clobber.
	if _, err := WriteStub(tmplPath, outDir, closedEvent()); err == nil {
		t.Error("WriteStub must refuse to clobber existing postmortem")
	}
}

func TestLoadRootCauseEnum_12(t *testing.T) {
	p := filepath.Join(repoRoot(t), "contracts", "postmortems", "root_cause_enum.yaml")
	e, err := LoadRootCauseEnum(p)
	if err != nil {
		t.Fatalf("LoadRootCauseEnum: %v", err)
	}
	if e.Count() != 12 {
		t.Errorf("root cause enum count = %d want 12 (SR4)", e.Count())
	}
	for _, id := range []string{"code_defect", "data_corruption", "security_incident", "unknown"} {
		if !e.IsValidRootCause(id) {
			t.Errorf("enum missing %q", id)
		}
	}
	if e.IsValidRootCause("aliens") {
		t.Error("unknown root cause must be invalid")
	}
}
