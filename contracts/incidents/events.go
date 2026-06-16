package incidents

import (
	"errors"
	"fmt"
	"time"
)

// Event type discriminators (the `type` field on the wire). Versioned;
// additive-only. statuspage-updater + postmortem-bot switch on these.
const (
	TypeIncidentDeclaredV1 = "incident.declared.v1"
	TypeIncidentUpdatedV1  = "incident.updated.v1"
	TypeIncidentClosedV1   = "incident.closed.v1"
)

// IncidentDeclaredV1 is emitted by incident-bot the moment an incident is
// declared (auto-classified from an alert, or manually). statuspage-updater
// consumes this to post a status-page incident + auto-banner for SEV0/SEV1.
//
// UserVisible drives the comms obligation: only user-visible SEV0/SEV1
// incidents auto-post to the public status page (SR02 §12AE.2). An internal
// SEV0 (e.g. an audit-hash mismatch with no user-facing symptom) still wakes
// on-call but does NOT necessarily raise a public banner — the status-page
// poster honors the matrix comms_obligation column.
type IncidentDeclaredV1 struct {
	Type        string    `json:"type"`         // == TypeIncidentDeclaredV1
	IncidentID  string    `json:"incident_id"`  // canonical id, e.g. "INC-2026-0531-0001"
	Severity    Severity  `json:"severity"`     // SEV0..SEV3
	Title       string    `json:"title"`        // short human title
	Summary     string    `json:"summary"`      // 1-2 sentence customer-safe summary
	Trigger     string    `json:"trigger"`      // what fired it (alert name / manual / classifier rule id)
	UserVisible bool      `json:"user_visible"` // gates public status-page posting
	Components  []string  `json:"components"`   // affected status-page components (gateway, auth, …)
	DeclaredAt  time.Time `json:"declared_at"`  // RFC3339
	ICUserID    string    `json:"ic_user_id"`   // assigned Incident Commander (may be empty at declare-time)
}

// IncidentUpdatedV1 is emitted on status transitions during an incident
// (investigating → identified → monitoring). Drives status-page updates.
type IncidentUpdatedV1 struct {
	Type        string    `json:"type"`        // == TypeIncidentUpdatedV1
	IncidentID  string    `json:"incident_id"`
	Severity    Severity  `json:"severity"`    // may have been re-classified
	Status      string    `json:"status"`      // investigating | identified | monitoring
	Message     string    `json:"message"`     // customer-safe update text
	UserVisible bool      `json:"user_visible"`
	UpdatedAt   time.Time `json:"updated_at"`
}

// IncidentClosedV1 is emitted when an incident is resolved/closed.
// postmortem-bot consumes this to create the postmortem stub; statuspage
// -updater consumes it to mark the status-page incident resolved.
type IncidentClosedV1 struct {
	Type            string    `json:"type"`             // == TypeIncidentClosedV1
	IncidentID      string    `json:"incident_id"`
	Severity        Severity  `json:"severity"`
	Title           string    `json:"title"`
	DeclaredAt      time.Time `json:"declared_at"`
	ResolvedAt      time.Time `json:"resolved_at"`
	UserVisible     bool      `json:"user_visible"`
	PostmortemDue   bool      `json:"postmortem_due"`    // true for SEV0/SEV1 per SR04
	ResolutionNote  string    `json:"resolution_note"`
}

// Valid status values for IncidentUpdatedV1.
var validStatuses = map[string]bool{
	"investigating": true,
	"identified":    true,
	"monitoring":    true,
}

// Validate checks an IncidentDeclaredV1 is well-formed before emission.
func (e IncidentDeclaredV1) Validate() error {
	if e.Type != TypeIncidentDeclaredV1 {
		return fmt.Errorf("incidents: declared event type=%q want %q", e.Type, TypeIncidentDeclaredV1)
	}
	if e.IncidentID == "" {
		return errors.New("incidents: declared event missing incident_id")
	}
	if !e.Severity.IsValid() {
		return fmt.Errorf("incidents: declared event invalid severity %q", e.Severity)
	}
	if e.Title == "" {
		return errors.New("incidents: declared event missing title")
	}
	if e.DeclaredAt.IsZero() {
		return errors.New("incidents: declared event missing declared_at")
	}
	return nil
}

// Validate checks an IncidentUpdatedV1.
func (e IncidentUpdatedV1) Validate() error {
	if e.Type != TypeIncidentUpdatedV1 {
		return fmt.Errorf("incidents: updated event type=%q want %q", e.Type, TypeIncidentUpdatedV1)
	}
	if e.IncidentID == "" {
		return errors.New("incidents: updated event missing incident_id")
	}
	if !e.Severity.IsValid() {
		return fmt.Errorf("incidents: updated event invalid severity %q", e.Severity)
	}
	if !validStatuses[e.Status] {
		return fmt.Errorf("incidents: updated event invalid status %q (want investigating|identified|monitoring)", e.Status)
	}
	if e.UpdatedAt.IsZero() {
		return errors.New("incidents: updated event missing updated_at")
	}
	return nil
}

// Validate checks an IncidentClosedV1.
func (e IncidentClosedV1) Validate() error {
	if e.Type != TypeIncidentClosedV1 {
		return fmt.Errorf("incidents: closed event type=%q want %q", e.Type, TypeIncidentClosedV1)
	}
	if e.IncidentID == "" {
		return errors.New("incidents: closed event missing incident_id")
	}
	if !e.Severity.IsValid() {
		return fmt.Errorf("incidents: closed event invalid severity %q", e.Severity)
	}
	if e.ResolvedAt.IsZero() {
		return errors.New("incidents: closed event missing resolved_at")
	}
	if !e.DeclaredAt.IsZero() && e.ResolvedAt.Before(e.DeclaredAt) {
		return errors.New("incidents: closed event resolved_at before declared_at")
	}
	return nil
}

// NewIncidentDeclaredV1 is a convenience constructor that stamps the type
// discriminator so callers cannot forget it.
func NewIncidentDeclaredV1(id string, sev Severity, title, summary, trigger string, userVisible bool, components []string, at time.Time, icUserID string) IncidentDeclaredV1 {
	return IncidentDeclaredV1{
		Type:        TypeIncidentDeclaredV1,
		IncidentID:  id,
		Severity:    sev,
		Title:       title,
		Summary:     summary,
		Trigger:     trigger,
		UserVisible: userVisible,
		Components:  components,
		DeclaredAt:  at,
		ICUserID:    icUserID,
	}
}
