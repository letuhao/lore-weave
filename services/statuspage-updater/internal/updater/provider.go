// Package updater implements L7.L.3 — the status-page updater. It consumes
// incident events (the shared contracts/incidents wire shapes that
// incident-bot emits) and drives the public status page.
//
// The Statuspage.io API is abstracted behind StatusPageClient (Q-L7L-1
// abstraction) so unit + integration tests run WITHOUT a live account. The
// real client is credential-gated via env vars and fails closed if missing.
package updater

import (
	"context"
	"fmt"
	"os"
)

// Impact mirrors Statuspage.io incident impact levels.
type Impact string

const (
	ImpactNone     Impact = "none"
	ImpactMinor    Impact = "minor"
	ImpactMajor    Impact = "major"
	ImpactCritical Impact = "critical"
)

// IncidentPost is the provider-agnostic status-page incident payload.
type IncidentPost struct {
	IncidentID    string
	Name          string
	Body          string
	Impact        Impact
	Status        string   // investigating | identified | monitoring | resolved
	ComponentIDs  []string // status-page component ids
	Banner        bool
}

// StatusPageClient is the provider façade. Real impl talks to Statuspage.io;
// tests inject a fake.
type StatusPageClient interface {
	// CreateIncident posts a new public incident and returns its provider id.
	CreateIncident(ctx context.Context, p IncidentPost) (providerIncidentID string, err error)
	// UpdateIncident appends an update to an existing incident.
	UpdateIncident(ctx context.Context, providerIncidentID string, p IncidentPost) error
	// ResolveIncident marks an incident resolved + clears its banner.
	ResolveIncident(ctx context.Context, providerIncidentID string, body string) error
}

// SlackConfig analog: Statuspage credentials from env (fail-closed).
type ProviderConfig struct {
	APIKey string // STATUSPAGE_API_KEY
	PageID string // STATUSPAGE_PAGE_ID
}

// LoadProviderConfigFromEnv reads the Statuspage.io credentials.
func LoadProviderConfigFromEnv() (ProviderConfig, error) {
	key := os.Getenv("STATUSPAGE_API_KEY")
	page := os.Getenv("STATUSPAGE_PAGE_ID")
	if key == "" || page == "" {
		return ProviderConfig{}, fmt.Errorf("statuspage-updater: STATUSPAGE_API_KEY + STATUSPAGE_PAGE_ID required (env-var only, fail closed)")
	}
	return ProviderConfig{APIKey: key, PageID: page}, nil
}

// statuspageIOClient is the real client. V1 scaffold — concrete HTTP calls
// land with the live account (tracked D-STATUSPAGE-LIVE-SMOKE). The interface
// + fail-closed credential gate are the load-bearing pieces.
type statuspageIOClient struct {
	cfg ProviderConfig
}

// NewStatuspageIOClient builds the real client. Requires credentials.
func NewStatuspageIOClient(cfg ProviderConfig) (StatusPageClient, error) {
	if cfg.APIKey == "" || cfg.PageID == "" {
		return nil, fmt.Errorf("statuspage-updater: refusing to build client without API key + page id")
	}
	return &statuspageIOClient{cfg: cfg}, nil
}

func (c *statuspageIOClient) CreateIncident(ctx context.Context, p IncidentPost) (string, error) {
	return "", fmt.Errorf("statuspage-updater: live Statuspage.io create not wired (D-STATUSPAGE-LIVE-SMOKE); incident=%s", p.IncidentID)
}

func (c *statuspageIOClient) UpdateIncident(ctx context.Context, providerIncidentID string, p IncidentPost) error {
	return fmt.Errorf("statuspage-updater: live Statuspage.io update not wired (D-STATUSPAGE-LIVE-SMOKE)")
}

func (c *statuspageIOClient) ResolveIncident(ctx context.Context, providerIncidentID string, body string) error {
	return fmt.Errorf("statuspage-updater: live Statuspage.io resolve not wired (D-STATUSPAGE-LIVE-SMOKE)")
}
