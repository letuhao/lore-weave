// Package comms_template implements L7.D.5 — pre-approved customer comms copy.
//
// SR2 problem 7: under incident pressure, ad-hoc copy is risky (wrong tone,
// premature root-cause claims, legal exposure). This package loads a set of
// PRE-APPROVED templates from infra/comms/templates/ (Q-L7-2 LOCKED location)
// and renders them with a small, fixed placeholder set. New templates require
// review before landing (Q-L7-2: formal legal-review workflow is V2+).
//
// Templates are i18n: each template file declares EN + VI bodies (V1 minimum
// per L7.L.4). Rendering picks the requested locale, falling back to EN.
package comms_template

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

// LocaleBody holds one locale's subject + body for a template.
type LocaleBody struct {
	Subject string `yaml:"subject"`
	Body    string `yaml:"body"`
}

// Template is one pre-approved comms template.
type Template struct {
	ID          string                `yaml:"id"`
	Description string                `yaml:"description"`
	Channel     string                `yaml:"channel"` // status_page | email | banner
	Severities  []string              `yaml:"severities"`
	Locales     map[string]LocaleBody `yaml:"locales"`
	// Placeholders the body legitimately uses ({{incident_id}}, etc.).
	Placeholders []string `yaml:"placeholders"`
}

// Library is the loaded set of templates keyed by id.
type Library struct {
	byID map[string]Template
}

// LoadLibrary loads every *.yaml template under dir.
func LoadLibrary(dir string) (*Library, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, fmt.Errorf("comms_template: read dir %s: %w", dir, err)
	}
	lib := &Library{byID: map[string]Template{}}
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".yaml") {
			continue
		}
		raw, err := os.ReadFile(filepath.Join(dir, e.Name()))
		if err != nil {
			return nil, fmt.Errorf("comms_template: read %s: %w", e.Name(), err)
		}
		var t Template
		if err := yaml.Unmarshal(raw, &t); err != nil {
			return nil, fmt.Errorf("comms_template: parse %s: %w", e.Name(), err)
		}
		if t.ID == "" {
			return nil, fmt.Errorf("comms_template: %s missing id", e.Name())
		}
		if _, dup := lib.byID[t.ID]; dup {
			return nil, fmt.Errorf("comms_template: duplicate template id %q", t.ID)
		}
		// V1 minimum: every template MUST carry EN + VI.
		if _, ok := t.Locales["en"]; !ok {
			return nil, fmt.Errorf("comms_template: %q missing required locale 'en'", t.ID)
		}
		if _, ok := t.Locales["vi"]; !ok {
			return nil, fmt.Errorf("comms_template: %q missing required locale 'vi' (V1 EN+VI minimum)", t.ID)
		}
		lib.byID[t.ID] = t
	}
	if len(lib.byID) == 0 {
		return nil, fmt.Errorf("comms_template: no templates found in %s", dir)
	}
	return lib, nil
}

// IDs returns the loaded template ids (sorted-insensitive; order not
// guaranteed — callers that need order should sort).
func (l *Library) IDs() []string {
	out := make([]string, 0, len(l.byID))
	for id := range l.byID {
		out = append(out, id)
	}
	return out
}

// Get returns a template by id.
func (l *Library) Get(id string) (Template, bool) {
	t, ok := l.byID[id]
	return t, ok
}

// Rendered is a rendered comms message.
type Rendered struct {
	Subject string
	Body    string
	Locale  string
}

// Render fills a template's placeholders for the given locale. Unknown
// locales fall back to EN. Returns an error if the template id is unknown or
// a required placeholder value is missing.
func (l *Library) Render(id, locale string, values map[string]string) (Rendered, error) {
	t, ok := l.byID[id]
	if !ok {
		return Rendered{}, fmt.Errorf("comms_template: unknown template %q", id)
	}
	body, ok := t.Locales[locale]
	usedLocale := locale
	if !ok {
		body = t.Locales["en"]
		usedLocale = "en"
	}
	// Ensure all declared placeholders have a value.
	for _, ph := range t.Placeholders {
		if _, present := values[ph]; !present {
			return Rendered{}, fmt.Errorf("comms_template: %q missing placeholder value %q", id, ph)
		}
	}
	subject := substitute(body.Subject, values)
	rendered := substitute(body.Body, values)
	// No unresolved {{...}} may remain.
	if strings.Contains(subject, "{{") || strings.Contains(rendered, "{{") {
		return Rendered{}, fmt.Errorf("comms_template: %q has unresolved placeholders after render", id)
	}
	return Rendered{Subject: subject, Body: rendered, Locale: usedLocale}, nil
}

func substitute(s string, values map[string]string) string {
	for k, v := range values {
		s = strings.ReplaceAll(s, "{{"+k+"}}", v)
	}
	return s
}
