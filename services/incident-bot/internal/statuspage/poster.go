// Package statuspage implements L7.D.4 — auto-posts to the status page
// (L7.L) for SEV0/SEV1 user-visible incidents.
//
// This is the incident-bot SIDE of the L7.D ↔ L7.L boundary. It does NOT
// talk to Statuspage.io directly; instead it decides — using the shared
// severity matrix (contracts/incidents) — whether the comms obligation
// requires a public post, and if so emits an IncidentDeclaredV1 onto the
// incident event stream. statuspage-updater (DPS 2, L7.L.3) consumes that
// same event and performs the actual provider call. This keeps the two
// services decoupled (Q-L7-1) and means the obligation logic has ONE home.
package statuspage

import (
	"context"
	"fmt"

	"github.com/loreweave/foundation/contracts/incidents"
)

// EventEmitter publishes incident events to the stream statuspage-updater
// subscribes to. Abstracted so tests don't need a live broker.
type EventEmitter interface {
	EmitIncidentDeclared(ctx context.Context, ev incidents.IncidentDeclaredV1) error
}

// Poster decides + emits.
type Poster struct {
	matrix  *incidents.SeverityMatrix
	emitter EventEmitter
}

// New builds a Poster. Fails closed on nil deps.
func New(matrix *incidents.SeverityMatrix, emitter EventEmitter) (*Poster, error) {
	if matrix == nil {
		return nil, fmt.Errorf("statuspage: nil severity matrix")
	}
	if emitter == nil {
		return nil, fmt.Errorf("statuspage: nil event emitter")
	}
	return &Poster{matrix: matrix, emitter: emitter}, nil
}

// Decision explains whether + why a status-page post is required.
type Decision struct {
	ShouldPost bool
	AutoBanner bool
	Reason     string
}

// Decide computes the comms obligation for an event WITHOUT side effects.
// This is the pure decision the integration test asserts.
func (p *Poster) Decide(ev incidents.IncidentDeclaredV1) Decision {
	shouldPost := p.matrix.RequiresStatusPage(ev.Severity, ev.UserVisible)
	banner := p.matrix.RequiresAutoBanner(ev.Severity, ev.UserVisible)
	reason := fmt.Sprintf("severity=%s user_visible=%v → post=%v banner=%v",
		ev.Severity, ev.UserVisible, shouldPost, banner)
	return Decision{ShouldPost: shouldPost, AutoBanner: banner, Reason: reason}
}

// MaybePost emits the incident event for status-page consumption iff the
// comms obligation requires it. Returns the Decision taken. A no-op (no
// obligation) is NOT an error.
func (p *Poster) MaybePost(ctx context.Context, ev incidents.IncidentDeclaredV1) (Decision, error) {
	if err := ev.Validate(); err != nil {
		return Decision{}, fmt.Errorf("statuspage: invalid event: %w", err)
	}
	d := p.Decide(ev)
	if !d.ShouldPost {
		return d, nil
	}
	if err := p.emitter.EmitIncidentDeclared(ctx, ev); err != nil {
		return d, fmt.Errorf("statuspage: emit incident event: %w", err)
	}
	return d, nil
}
