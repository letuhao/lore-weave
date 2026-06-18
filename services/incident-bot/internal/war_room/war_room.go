// Package war_room implements L7.D.3 — war-room channel creation.
//
// On incident declaration the bot creates a dedicated `#incident-<id>`
// channel and invites the IC, the fixer, and the relevant teams. The Slack
// API is abstracted behind ChannelProvider so unit tests run without a live
// workspace and so a future provider swap (Discord, Mattermost) is a one-
// interface change.
//
// Acceptance: war-room creation < 30s after incident declaration. The
// in-process orchestration here is sub-millisecond; the 30s budget is for
// the live provider round-trip, asserted in the integration test against a
// fake provider with an injected latency bound.
package war_room

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/loreweave/foundation/contracts/incidents"
)

// ChannelProvider is the Slack (or other chat) façade. The real
// implementation lives behind an env-var-configured client (see
// slackProvider); tests inject a fake.
type ChannelProvider interface {
	// CreateChannel creates a channel by name and returns its id.
	CreateChannel(ctx context.Context, name, topic string) (channelID string, err error)
	// Invite adds users to a channel.
	Invite(ctx context.Context, channelID string, userIDs []string) error
	// PostMessage posts a message (used for the severity card).
	PostMessage(ctx context.Context, channelID, text string) error
}

// Roster is the set of people to pull into the war room.
type Roster struct {
	ICUserID    string   // Incident Commander (separate from fixer per SR2 §12AE.2)
	FixerUserID string   // the engineer fixing
	TeamUserIDs []string // relevant team members
}

// Manager orchestrates war-room creation.
type Manager struct {
	provider ChannelProvider
}

// New builds a Manager. Returns an error on a nil provider (fail closed).
func New(provider ChannelProvider) (*Manager, error) {
	if provider == nil {
		return nil, fmt.Errorf("war_room: nil channel provider")
	}
	return &Manager{provider: provider}, nil
}

// ChannelName derives the canonical war-room channel name from an incident
// id. Slack channel names are lowercase, no spaces, ≤80 chars.
func ChannelName(incidentID string) string {
	clean := strings.ToLower(incidentID)
	clean = strings.ReplaceAll(clean, " ", "-")
	name := "incident-" + clean
	if len(name) > 80 {
		name = name[:80]
	}
	return name
}

// CreateResult is returned to the caller (and audited).
type CreateResult struct {
	ChannelID   string
	ChannelName string
	Invited     []string
	ElapsedMS   int64
}

// Create makes the war-room channel, invites the roster, and posts the
// severity card. now is injected so the elapsed-time assertion is
// deterministic in tests.
func (m *Manager) Create(ctx context.Context, ev incidents.IncidentDeclaredV1, roster Roster, now func() time.Time) (*CreateResult, error) {
	if err := ev.Validate(); err != nil {
		return nil, fmt.Errorf("war_room: invalid incident event: %w", err)
	}
	start := now()

	name := ChannelName(ev.IncidentID)
	topic := fmt.Sprintf("%s | %s | IC: %s", ev.Severity, ev.Title, roster.ICUserID)
	chID, err := m.provider.CreateChannel(ctx, name, topic)
	if err != nil {
		return nil, fmt.Errorf("war_room: create channel %q: %w", name, err)
	}

	invitees := dedupeNonEmpty(append([]string{roster.ICUserID, roster.FixerUserID}, roster.TeamUserIDs...))
	if len(invitees) > 0 {
		if err := m.provider.Invite(ctx, chID, invitees); err != nil {
			return nil, fmt.Errorf("war_room: invite roster: %w", err)
		}
	}

	if err := m.provider.PostMessage(ctx, chID, severityCard(ev, roster)); err != nil {
		return nil, fmt.Errorf("war_room: post severity card: %w", err)
	}

	return &CreateResult{
		ChannelID:   chID,
		ChannelName: name,
		Invited:     invitees,
		ElapsedMS:   now().Sub(start).Milliseconds(),
	}, nil
}

// severityCard renders the pinned incident card posted to the war room.
func severityCard(ev incidents.IncidentDeclaredV1, roster Roster) string {
	var b strings.Builder
	fmt.Fprintf(&b, ":rotating_light: *%s — %s*\n", ev.Severity, ev.Title)
	fmt.Fprintf(&b, "Incident: `%s`\n", ev.IncidentID)
	fmt.Fprintf(&b, "Trigger: %s\n", ev.Trigger)
	fmt.Fprintf(&b, "IC: %s | Fixer: %s\n", orNone(roster.ICUserID), orNone(roster.FixerUserID))
	if ev.UserVisible {
		b.WriteString("User-visible: YES — status-page comms obligation active\n")
	} else {
		b.WriteString("User-visible: no\n")
	}
	if ev.Summary != "" {
		fmt.Fprintf(&b, "Summary: %s\n", ev.Summary)
	}
	return b.String()
}

func orNone(s string) string {
	if s == "" {
		return "(unassigned)"
	}
	return s
}

func dedupeNonEmpty(in []string) []string {
	seen := make(map[string]bool, len(in))
	out := make([]string, 0, len(in))
	for _, s := range in {
		if s == "" || seen[s] {
			continue
		}
		seen[s] = true
		out = append(out, s)
	}
	return out
}
