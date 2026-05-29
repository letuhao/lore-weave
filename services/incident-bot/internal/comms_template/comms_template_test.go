package comms_template

import (
	"path/filepath"
	"strings"
	"testing"
)

func templatesDir(t *testing.T) string {
	t.Helper()
	return filepath.Join("..", "..", "..", "..", "infra", "comms", "templates")
}

func TestLoadLibrary(t *testing.T) {
	lib, err := LoadLibrary(templatesDir(t))
	if err != nil {
		t.Fatalf("LoadLibrary: %v", err)
	}
	want := []string{"incident_investigating", "incident_identified", "incident_resolved", "gdpr_breach_notice"}
	for _, id := range want {
		if _, ok := lib.Get(id); !ok {
			t.Errorf("library missing template %q", id)
		}
	}
}

func TestLoadLibrary_RequiresENandVI(t *testing.T) {
	lib, err := LoadLibrary(templatesDir(t))
	if err != nil {
		t.Fatalf("LoadLibrary: %v", err)
	}
	for _, id := range lib.IDs() {
		tpl, _ := lib.Get(id)
		if _, ok := tpl.Locales["en"]; !ok {
			t.Errorf("%q missing en", id)
		}
		if _, ok := tpl.Locales["vi"]; !ok {
			t.Errorf("%q missing vi (V1 EN+VI minimum)", id)
		}
	}
}

func TestRender_EN(t *testing.T) {
	lib, _ := LoadLibrary(templatesDir(t))
	r, err := lib.Render("incident_investigating", "en", map[string]string{
		"incident_id": "INC-1", "components": "gateway", "started_at": "12:00",
	})
	if err != nil {
		t.Fatalf("Render: %v", err)
	}
	if r.Locale != "en" {
		t.Errorf("locale = %q", r.Locale)
	}
	if !strings.Contains(r.Body, "gateway") || !strings.Contains(r.Body, "INC-1") {
		t.Errorf("body not substituted: %q", r.Body)
	}
	if strings.Contains(r.Body, "{{") {
		t.Errorf("unresolved placeholder: %q", r.Body)
	}
}

func TestRender_VI(t *testing.T) {
	lib, _ := LoadLibrary(templatesDir(t))
	r, err := lib.Render("incident_investigating", "vi", map[string]string{
		"incident_id": "INC-1", "components": "cổng", "started_at": "12:00",
	})
	if err != nil {
		t.Fatalf("Render vi: %v", err)
	}
	if r.Locale != "vi" {
		t.Errorf("locale = %q want vi", r.Locale)
	}
	if !strings.Contains(r.Body, "điều tra") {
		t.Errorf("vi body not used: %q", r.Body)
	}
}

func TestRender_UnknownLocaleFallsBackEN(t *testing.T) {
	lib, _ := LoadLibrary(templatesDir(t))
	r, err := lib.Render("incident_identified", "fr", map[string]string{
		"incident_id": "INC-1", "components": "gateway",
	})
	if err != nil {
		t.Fatalf("Render fr: %v", err)
	}
	if r.Locale != "en" {
		t.Errorf("unknown locale should fall back to en, got %q", r.Locale)
	}
}

func TestRender_MissingPlaceholder(t *testing.T) {
	lib, _ := LoadLibrary(templatesDir(t))
	_, err := lib.Render("incident_investigating", "en", map[string]string{
		"incident_id": "INC-1", // missing components + started_at
	})
	if err == nil {
		t.Error("missing placeholder must error")
	}
}

func TestRender_UnknownTemplate(t *testing.T) {
	lib, _ := LoadLibrary(templatesDir(t))
	if _, err := lib.Render("nope", "en", nil); err == nil {
		t.Error("unknown template must error")
	}
}
