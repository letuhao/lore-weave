// Package incidentflow is the PUBLIC orchestration surface of incident-bot.
//
// The internal/* packages (severity_classifier, war_room, statuspage,
// ic_role, gdpr_breach_flow, comms_template) are encapsulated; this package
// composes them into the declared-incident pipeline so external consumers
// (the cross-service integration test, a future BFF endpoint) can drive the
// flow without reaching into internal/ (which Go forbids across modules).
//
// It re-exports the small set of types callers need (Signal, Roster,
// channel/emitter interfaces) so the integration test depends only on this
// public package + the contracts/incidents wire types.
package incidentflow

import (
	"context"
	"fmt"
	"time"

	"github.com/loreweave/foundation/contracts/incidents"
	"github.com/loreweave/foundation/services/incident-bot/internal/ic_role"
	"github.com/loreweave/foundation/services/incident-bot/internal/severity_classifier"
	"github.com/loreweave/foundation/services/incident-bot/internal/statuspage"
	"github.com/loreweave/foundation/services/incident-bot/internal/war_room"
)

// Re-exported types so callers need only import this package.
type (
	// Signal is an inbound alert/declaration to classify.
	Signal = severity_classifier.Signal
	// Roster is the war-room invite set.
	Roster = war_room.Roster
	// ChannelProvider is the war-room chat façade (Slack, etc.).
	ChannelProvider = war_room.ChannelProvider
	// EventEmitter publishes incident events for statuspage-updater.
	EventEmitter = statuspage.EventEmitter
)

// Engine composes the declared-incident pipeline.
type Engine struct {
	classifier *severity_classifier.Classifier
	warRoom    *war_room.Manager
	poster     *statuspage.Poster
}

// New builds an Engine from a loaded matrix + injected providers.
func New(matrix *incidents.SeverityMatrix, channels ChannelProvider, emitter EventEmitter) (*Engine, error) {
	clf, err := severity_classifier.New(matrix)
	if err != nil {
		return nil, err
	}
	wr, err := war_room.New(channels)
	if err != nil {
		return nil, err
	}
	poster, err := statuspage.New(matrix, emitter)
	if err != nil {
		return nil, err
	}
	return &Engine{classifier: clf, warRoom: wr, poster: poster}, nil
}

// DeclareResult is the outcome of declaring an incident.
type DeclareResult struct {
	Event       incidents.IncidentDeclaredV1
	ClassReason string
	WarRoom     *war_room.CreateResult
	StatusPage  statuspage.Decision
	Assignment  *ic_role.Assignment
}

// Declare runs the full pipeline: classify → build event → create war room →
// emit status-page obligation → assign IC. incidentID + roster are supplied
// by the caller (id allocation + roster lookup live outside this engine).
// now is injected for deterministic timing.
func (e *Engine) Declare(ctx context.Context, incidentID string, sig Signal, title, summary string, components []string, roster Roster, now func() time.Time) (*DeclareResult, error) {
	if incidentID == "" {
		return nil, fmt.Errorf("incidentflow: empty incident id")
	}
	cls := e.classifier.Classify(sig)

	ev := incidents.NewIncidentDeclaredV1(
		incidentID, cls.Severity, title, summary, cls.MatchedTrigger,
		cls.UserVisible, components, now(), roster.ICUserID)
	if err := ev.Validate(); err != nil {
		return nil, fmt.Errorf("incidentflow: built invalid event: %w", err)
	}

	wrRes, err := e.warRoom.Create(ctx, ev, roster, now)
	if err != nil {
		return nil, fmt.Errorf("incidentflow: war room: %w", err)
	}

	dec, err := e.poster.MaybePost(ctx, ev)
	if err != nil {
		return nil, fmt.Errorf("incidentflow: status page: %w", err)
	}

	assign, err := ic_role.Assign(incidentID, roster.ICUserID, roster.FixerUserID, now())
	if err != nil {
		return nil, fmt.Errorf("incidentflow: IC assign: %w", err)
	}

	return &DeclareResult{
		Event:       ev,
		ClassReason: cls.Reason,
		WarRoom:     wrRes,
		StatusPage:  dec,
		Assignment:  assign,
	}, nil
}
