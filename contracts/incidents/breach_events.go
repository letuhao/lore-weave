package incidents

import (
	"errors"
	"fmt"
	"time"
)

// GDPR Art.33 personal-data-breach event discriminators (L7.D.7). incident-bot
// EMITS these; a downstream consumer delivers the DPO notice + persists the
// timeline (Q-L7-1: incident-bot decides + emits — it does not deliver/persist).
const (
	TypeGDPRBreachOpenedV1      = "gdpr.breach.opened.v1"
	TypeGDPRDPONoticeRequiredV1 = "gdpr.dpo_notice_required.v1"
	TypeGDPRBreachDeadlineV1    = "gdpr.breach.deadline.v1"
)

// Breach deadline states for GDPRBreachDeadlineV1.State.
const (
	BreachDeadlineApproaching = "approaching"
	BreachDeadlineMissed      = "missed"
)

// GDPRBreachOpenedV1 — emitted when a personal-data breach is declared and the
// Art.33 72h clock starts. It is the authoritative timeline anchor a durable
// consumer can replay to rebuild the deadline monitor after a restart.
type GDPRBreachOpenedV1 struct {
	Type           string    `json:"type"`            // == TypeGDPRBreachOpenedV1
	IncidentID     string    `json:"incident_id"`     // canonical id
	DetectedAt     time.Time `json:"detected_at"`     // 72h clock anchor (operator-attested, not client-trusted)
	Deadline       time.Time `json:"deadline"`        // DetectedAt + 72h
	DataCategories string    `json:"data_categories"` // e.g. "email, display_name"
	AffectedCount  int       `json:"affected_count"`
}

// GDPRDPONoticeRequiredV1 — the DPO-notification OBLIGATION. incident-bot emits
// this; a delivery consumer (tracked: D-BREACH-DELIVERY-CONSUMER) sends the
// actual email/Slack. EMISSION IS NOT DELIVERY — never read this as "the DPO
// was notified", only as "a notice is required + has been queued".
type GDPRDPONoticeRequiredV1 struct {
	Type       string    `json:"type"` // == TypeGDPRDPONoticeRequiredV1
	IncidentID string    `json:"incident_id"`
	Subject    string    `json:"subject"`
	Body       string    `json:"body"`
	Deadline   time.Time `json:"deadline"`
}

// GDPRBreachDeadlineV1 — emitted by the deadline monitor when an open breach
// crosses the approaching (<=12h) or missed (<=0) threshold.
type GDPRBreachDeadlineV1 struct {
	Type                 string `json:"type"` // == TypeGDPRBreachDeadlineV1
	IncidentID           string `json:"incident_id"`
	State                string `json:"state"`                  // approaching | missed
	TimeRemainingSeconds int64  `json:"time_remaining_seconds"` // negative once missed
}

// Validate checks a GDPRBreachOpenedV1 is well-formed before emission.
func (e GDPRBreachOpenedV1) Validate() error {
	if e.Type != TypeGDPRBreachOpenedV1 {
		return fmt.Errorf("incidents: breach-opened event type=%q want %q", e.Type, TypeGDPRBreachOpenedV1)
	}
	if e.IncidentID == "" {
		return errors.New("incidents: breach-opened event missing incident_id")
	}
	if e.DetectedAt.IsZero() {
		return errors.New("incidents: breach-opened event missing detected_at (72h anchor)")
	}
	if !e.Deadline.After(e.DetectedAt) {
		return errors.New("incidents: breach-opened event deadline must be after detected_at")
	}
	if e.AffectedCount < 0 {
		return fmt.Errorf("incidents: breach-opened event affected_count must be >= 0 (got %d)", e.AffectedCount)
	}
	return nil
}

// Validate checks a GDPRDPONoticeRequiredV1.
func (e GDPRDPONoticeRequiredV1) Validate() error {
	if e.Type != TypeGDPRDPONoticeRequiredV1 {
		return fmt.Errorf("incidents: dpo-notice event type=%q want %q", e.Type, TypeGDPRDPONoticeRequiredV1)
	}
	if e.IncidentID == "" {
		return errors.New("incidents: dpo-notice event missing incident_id")
	}
	if e.Subject == "" || e.Body == "" {
		return errors.New("incidents: dpo-notice event missing subject/body")
	}
	return nil
}

// Validate checks a GDPRBreachDeadlineV1.
func (e GDPRBreachDeadlineV1) Validate() error {
	if e.Type != TypeGDPRBreachDeadlineV1 {
		return fmt.Errorf("incidents: breach-deadline event type=%q want %q", e.Type, TypeGDPRBreachDeadlineV1)
	}
	if e.IncidentID == "" {
		return errors.New("incidents: breach-deadline event missing incident_id")
	}
	if e.State != BreachDeadlineApproaching && e.State != BreachDeadlineMissed {
		return fmt.Errorf("incidents: breach-deadline event invalid state %q (want approaching|missed)", e.State)
	}
	return nil
}

// NewGDPRBreachOpenedV1 stamps the type discriminator.
func NewGDPRBreachOpenedV1(incidentID string, detectedAt, deadline time.Time, dataCategories string, affectedCount int) GDPRBreachOpenedV1 {
	return GDPRBreachOpenedV1{
		Type:           TypeGDPRBreachOpenedV1,
		IncidentID:     incidentID,
		DetectedAt:     detectedAt,
		Deadline:       deadline,
		DataCategories: dataCategories,
		AffectedCount:  affectedCount,
	}
}

// NewGDPRDPONoticeRequiredV1 stamps the type discriminator.
func NewGDPRDPONoticeRequiredV1(incidentID, subject, body string, deadline time.Time) GDPRDPONoticeRequiredV1 {
	return GDPRDPONoticeRequiredV1{
		Type:       TypeGDPRDPONoticeRequiredV1,
		IncidentID: incidentID,
		Subject:    subject,
		Body:       body,
		Deadline:   deadline,
	}
}

// NewGDPRBreachDeadlineV1 stamps the type discriminator.
func NewGDPRBreachDeadlineV1(incidentID, state string, timeRemaining time.Duration) GDPRBreachDeadlineV1 {
	return GDPRBreachDeadlineV1{
		Type:                 TypeGDPRBreachDeadlineV1,
		IncidentID:           incidentID,
		State:                state,
		TimeRemainingSeconds: int64(timeRemaining.Seconds()),
	}
}
