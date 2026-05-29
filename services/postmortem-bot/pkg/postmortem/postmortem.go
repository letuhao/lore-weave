// Package postmortem is the PUBLIC surface of postmortem-bot.
//
// The internal/generator package is encapsulated; this package re-exports
// the stub-generation entry points so external consumers (the cross-service
// integration test, a future ops endpoint) can create postmortem stubs
// without importing internal/ (forbidden across module boundaries).
package postmortem

import (
	"github.com/loreweave/foundation/contracts/incidents"
	"github.com/loreweave/foundation/services/postmortem-bot/internal/generator"
)

// RootCauseEnum re-exports the loaded taxonomy validator.
type RootCauseEnum = generator.RootCauseEnum

// LoadRootCauseEnum loads + validates the SR4 12-enum taxonomy.
func LoadRootCauseEnum(path string) (*RootCauseEnum, error) {
	return generator.LoadRootCauseEnum(path)
}

// Render fills the template body for a closed incident (no filesystem I/O).
func Render(templateBody string, ev incidents.IncidentClosedV1) (string, error) {
	return generator.Render(templateBody, ev)
}

// WriteStub renders + writes the postmortem stub to outDir, refusing to
// clobber an existing file.
func WriteStub(templatePath, outDir string, ev incidents.IncidentClosedV1) (string, error) {
	return generator.WriteStub(templatePath, outDir, ev)
}

// StubPath returns the canonical postmortem path for an incident id.
func StubPath(dir, incidentID string) string {
	return generator.StubPath(dir, incidentID)
}
