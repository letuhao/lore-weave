// Package statusflow is the PUBLIC surface of statuspage-updater.
//
// The internal/* packages are encapsulated; this package re-exports the
// updater + its config loaders so external consumers (the cross-service
// integration test, a future event-consumer wiring) can drive the status-page
// flow without importing internal/ (forbidden across module boundaries).
package statusflow

import (
	"github.com/loreweave/foundation/services/statuspage-updater/internal/config"
	"github.com/loreweave/foundation/services/statuspage-updater/internal/updater"
)

// Re-exported types.
type (
	Updater          = updater.Updater
	StatusPageClient = updater.StatusPageClient
	IncidentPost     = updater.IncidentPost
	Impact           = updater.Impact
	Components       = config.Components
	BannerConfig     = config.BannerConfig
	ProviderConfig   = updater.ProviderConfig
)

// Impact level re-exports.
const (
	ImpactNone     = updater.ImpactNone
	ImpactMinor    = updater.ImpactMinor
	ImpactMajor    = updater.ImpactMajor
	ImpactCritical = updater.ImpactCritical
)

// LoadComponents loads components.yaml.
func LoadComponents(path string) (*Components, error) { return config.LoadComponents(path) }

// LoadBannerConfig loads banner-config.yaml.
func LoadBannerConfig(path string) (*BannerConfig, error) { return config.LoadBannerConfig(path) }

// New builds an Updater from a client + loaded config.
func New(client StatusPageClient, components *Components, banner *BannerConfig) (*Updater, error) {
	return updater.New(client, components, banner)
}

// LoadProviderConfigFromEnv reads Statuspage.io credentials (fail-closed).
func LoadProviderConfigFromEnv() (ProviderConfig, error) {
	return updater.LoadProviderConfigFromEnv()
}

// NewStatuspageIOClient builds the real (credential-gated) client.
func NewStatuspageIOClient(cfg ProviderConfig) (StatusPageClient, error) {
	return updater.NewStatuspageIOClient(cfg)
}
