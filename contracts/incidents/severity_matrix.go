package incidents

import (
	"errors"
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

// CommsObligation is the per-severity comms policy row. Values are
// "required" | "conditional" | "none" for the textual obligations, and
// bool for the flags.
type CommsObligation struct {
	StatusPage      string `yaml:"status_page"`
	CustomerEmail   string `yaml:"customer_email"`
	AutoBanner      bool   `yaml:"auto_banner"`
	GDPRBreachCheck bool   `yaml:"gdpr_breach_check"`
}

// SeverityRow is one row of severity_matrix.yaml.
type SeverityRow struct {
	ID                  Severity        `yaml:"id"`
	Name                string          `yaml:"name"`
	Description         string          `yaml:"description"`
	TTAMinutes          int             `yaml:"tta_minutes"`
	PagerDutyService    string          `yaml:"pagerduty_service"`
	CommsObligation     CommsObligation `yaml:"comms_obligation"`
	AutoClassifyTriggers []string       `yaml:"auto_classify_triggers"`
}

// SeverityMatrix is the top-level wrapper of severity_matrix.yaml.
type SeverityMatrix struct {
	Version               int           `yaml:"version"`
	ShippedCycle          int           `yaml:"shipped_cycle"`
	ExpectedSeverityCount int           `yaml:"expected_severity_count"`
	Severities            []SeverityRow `yaml:"severities"`

	// byID is the lookup built at load time.
	byID      map[Severity]*SeverityRow
	byTrigger map[string]Severity
}

// LoadSeverityMatrix reads + validates the matrix from path.
func LoadSeverityMatrix(path string) (*SeverityMatrix, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("incidents: read severity_matrix %s: %w", path, err)
	}
	var m SeverityMatrix
	if err := yaml.Unmarshal(raw, &m); err != nil {
		return nil, fmt.Errorf("incidents: parse severity_matrix %s: %w", path, err)
	}
	if err := m.validateAndIndex(); err != nil {
		return nil, err
	}
	return &m, nil
}

func (m *SeverityMatrix) validateAndIndex() error {
	if m.Version == 0 {
		return errors.New("incidents: severity_matrix missing version")
	}
	if m.ExpectedSeverityCount > 0 && len(m.Severities) != m.ExpectedSeverityCount {
		return fmt.Errorf(
			"incidents: severity_matrix drift — expected_severity_count=%d but got %d rows",
			m.ExpectedSeverityCount, len(m.Severities),
		)
	}
	m.byID = make(map[Severity]*SeverityRow, len(m.Severities))
	m.byTrigger = make(map[string]Severity)
	for i := range m.Severities {
		row := &m.Severities[i]
		if !row.ID.IsValid() {
			return fmt.Errorf("incidents: severity_matrix row #%d invalid id %q", i, row.ID)
		}
		if _, dup := m.byID[row.ID]; dup {
			return fmt.Errorf("incidents: severity_matrix duplicate row for %s", row.ID)
		}
		if row.TTAMinutes <= 0 {
			return fmt.Errorf("incidents: severity_matrix %s: tta_minutes must be > 0", row.ID)
		}
		m.byID[row.ID] = row
		for _, trig := range row.AutoClassifyTriggers {
			if existing, dup := m.byTrigger[trig]; dup {
				return fmt.Errorf(
					"incidents: severity_matrix trigger %q maps to both %s and %s",
					trig, existing, row.ID,
				)
			}
			m.byTrigger[trig] = row.ID
		}
	}
	// All 4 canonical severities must be present.
	for _, sev := range allSeverities {
		if _, ok := m.byID[sev]; !ok {
			return fmt.Errorf("incidents: severity_matrix missing required severity %s", sev)
		}
	}
	return nil
}

// Row returns the matrix row for a severity, or (nil, false).
func (m *SeverityMatrix) Row(s Severity) (*SeverityRow, bool) {
	r, ok := m.byID[s]
	return r, ok
}

// SeverityForTrigger maps an auto-classify trigger string to its severity.
// Returns ("", false) for an unknown trigger.
func (m *SeverityMatrix) SeverityForTrigger(trigger string) (Severity, bool) {
	s, ok := m.byTrigger[trigger]
	return s, ok
}

// TTAMinutes returns the time-to-acknowledge budget for a severity.
func (m *SeverityMatrix) TTAMinutes(s Severity) (int, bool) {
	if r, ok := m.byID[s]; ok {
		return r.TTAMinutes, true
	}
	return 0, false
}

// RequiresStatusPage reports whether a declared incident must (or may, when
// "conditional" + userVisible) raise a public status-page entry. This is the
// single decision point statuspage-updater + incident-bot share.
func (m *SeverityMatrix) RequiresStatusPage(s Severity, userVisible bool) bool {
	r, ok := m.byID[s]
	if !ok {
		return false
	}
	switch r.CommsObligation.StatusPage {
	case "required":
		return userVisible
	case "conditional":
		return userVisible
	default: // "none"
		return false
	}
}

// RequiresAutoBanner reports whether SEV0/SEV1 auto-banner fires.
func (m *SeverityMatrix) RequiresAutoBanner(s Severity, userVisible bool) bool {
	r, ok := m.byID[s]
	if !ok {
		return false
	}
	return r.CommsObligation.AutoBanner && userVisible
}
