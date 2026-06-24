package deliver

import (
	"context"
	"errors"
	"fmt"
)

// SlackNotifier delivers the DPO notice to a Slack compliance channel. Like
// incident-bot's war_room slack_provider, V1 is a FAIL-CLOSED SCAFFOLD: the
// credential gate + the Notifier contract are the load-bearing pieces, but the live
// chat.postMessage round-trip is deferred (no dev creds) — D-BREACH-SLACK-LIVE. It is
// breach-notifier's OWN client by design (boundary: each service owns its provider; we
// do NOT import incident-bot's internal war_room). It is OPT-IN (main selects it only
// when explicitly configured) so its current not-wired failure never blocks the
// default LogNotifier path.
type SlackNotifier struct {
	botToken string
	channel  string
}

// NewSlackNotifier fails closed without a bot token (B6: provider creds via env only).
func NewSlackNotifier(botToken, channel string) (*SlackNotifier, error) {
	if botToken == "" {
		return nil, errors.New("deliver: refusing to build Slack notifier without SLACK_BOT_TOKEN")
	}
	if channel == "" {
		channel = "#compliance"
	}
	return &SlackNotifier{botToken: botToken, channel: channel}, nil
}

var _ Notifier = (*SlackNotifier)(nil)

// Deliver is a scaffold: it returns an error (does NOT pretend success) so the
// obligation is recorded as failed + re-delivered, never falsely confirmed. The real
// chat.postMessage call lands with the live workspace (D-BREACH-SLACK-LIVE).
func (s *SlackNotifier) Deliver(_ context.Context, n DPONotice) (string, error) {
	return "", fmt.Errorf("deliver: live Slack chat.postMessage to %s not wired (D-BREACH-SLACK-LIVE); incident=%s", s.channel, n.IncidentID)
}
