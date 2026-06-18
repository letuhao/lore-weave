package deployclass

import "testing"

func TestClassify_Patch_SingleServiceNoSchema(t *testing.T) {
	got := Classify(Signals{ChangedFiles: []string{
		"services/auth-service/internal/handler/login.go",
		"services/auth-service/internal/handler/login_test.go",
	}})
	if got != Patch {
		t.Errorf("got %q want patch", got)
	}
}

func TestClassify_Minor_SingleServiceWithMigration(t *testing.T) {
	got := Classify(Signals{ChangedFiles: []string{
		"services/book-service/internal/store/store.go",
		"migrations/book/031_add_col.up.sql",
		"migrations/book/031_add_col.down.sql",
	}})
	if got != Minor {
		t.Errorf("got %q want minor", got)
	}
}

func TestClassify_Minor_SingleServiceWithConfig(t *testing.T) {
	got := Classify(Signals{ChangedFiles: []string{
		"services/chat-service/app/main.py",
		"services/chat-service/config/limits.yaml",
	}})
	if got != Minor {
		t.Errorf("got %q want minor", got)
	}
}

func TestClassify_Major_MultiService(t *testing.T) {
	got := Classify(Signals{ChangedFiles: []string{
		"services/auth-service/internal/a.go",
		"services/book-service/internal/b.go",
	}})
	if got != Major {
		t.Errorf("got %q want major", got)
	}
}

func TestClassify_Minor_NewEndpointInContractsAPI(t *testing.T) {
	// §12AH.2: a non-breaking new endpoint in contracts/api/* is MINOR.
	got := Classify(Signals{ChangedFiles: []string{
		"services/book-service/internal/a.go",
		"contracts/api/book.openapi.yaml",
	}})
	if got != Minor {
		t.Errorf("got %q want minor (non-breaking contracts/api/ endpoint)", got)
	}
}

func TestClassify_Major_BreakingContractsAPI(t *testing.T) {
	// A contracts/api/ change flagged contract-breaking is MAJOR.
	got := Classify(Signals{
		ChangedFiles:     []string{"services/book-service/internal/a.go", "contracts/api/book.openapi.yaml"},
		ContractBreaking: true,
	})
	if got != Major {
		t.Errorf("got %q want major (breaking contracts/api change)", got)
	}
}

func TestClassify_Major_InternalContractChange(t *testing.T) {
	// A contracts/* change OUTSIDE contracts/api/ (internal wire shape) is MAJOR.
	got := Classify(Signals{ChangedFiles: []string{
		"services/book-service/internal/a.go",
		"contracts/events/book_events.go",
	}})
	if got != Major {
		t.Errorf("got %q want major (internal contract wire-shape change)", got)
	}
}

func TestClassify_Major_SchemaBreaking(t *testing.T) {
	got := Classify(Signals{
		ChangedFiles:   []string{"services/book-service/internal/a.go"},
		SchemaBreaking: true,
	})
	if got != Major {
		t.Errorf("got %q want major (schema-breaking)", got)
	}
}

func TestClassify_Emergency_LabelPlusIncident(t *testing.T) {
	got := Classify(Signals{
		ChangedFiles:   []string{"services/auth-service/internal/a.go", "services/book-service/internal/b.go"},
		EmergencyLabel: true,
		IncidentID:     "INC-2026-0531-0001",
	})
	if got != Emergency {
		t.Errorf("got %q want emergency (label + incident — must win over multi-service major)", got)
	}
}

func TestClassify_Emergency_LabelPlusSecurityFinding(t *testing.T) {
	got := Classify(Signals{
		ChangedFiles:      []string{"services/auth-service/internal/a.go"},
		EmergencyLabel:    true,
		SecurityFindingID: "SEC-2026-0007",
	})
	if got != Emergency {
		t.Errorf("got %q want emergency", got)
	}
}

func TestClassify_Emergency_LabelWithoutRefIsNotEmergency(t *testing.T) {
	// §12AH.2: emergency requires the label AND a reference. Label alone is not
	// enough — falls through to its blast-radius class.
	got := Classify(Signals{
		ChangedFiles:   []string{"services/auth-service/internal/a.go"},
		EmergencyLabel: true,
	})
	if got != Patch {
		t.Errorf("got %q want patch (emergency label without incident/security ref)", got)
	}
}

func TestServicesTouched_DistinctSorted(t *testing.T) {
	got := ServicesTouched([]string{
		"services/world-service/src/a.rs",
		"services/auth-service/internal/b.go",
		"services/world-service/src/c.rs",
		"docs/readme.md",
		"services/", // malformed; ignored
	})
	if len(got) != 2 || got[0] != "auth-service" || got[1] != "world-service" {
		t.Errorf("got %v want [auth-service world-service]", got)
	}
}

func TestClassify_DocsOnly_IsPatch(t *testing.T) {
	got := Classify(Signals{ChangedFiles: []string{"docs/raid/CYCLE_LOG.md"}})
	if got != Patch {
		t.Errorf("got %q want patch (zero services)", got)
	}
}

func TestClass_Valid_And_CanaryRequired(t *testing.T) {
	if !Major.CanaryRequired() {
		t.Error("major must require canary")
	}
	for _, c := range []Class{Patch, Minor, Emergency} {
		if c.CanaryRequired() {
			t.Errorf("%q must not require canary", c)
		}
	}
	if Class("bogus").Valid() {
		t.Error("bogus must be invalid")
	}
}
