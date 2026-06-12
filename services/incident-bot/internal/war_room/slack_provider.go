package war_room

import (
	"context"
	"fmt"
	"os"
)

// SlackConfig is the env-var-sourced Slack configuration. The bot token is
// NEVER hardcoded; the service fails to start if it is missing (B6 rule:
// external provider creds via env vars only, fail-closed).
type SlackConfig struct {
	BotToken string // SLACK_BOT_TOKEN
}

// LoadSlackConfigFromEnv reads SLACK_BOT_TOKEN. Returns an error (not a
// panic) so main() can decide whether war-room creation is enabled.
func LoadSlackConfigFromEnv() (SlackConfig, error) {
	tok := os.Getenv("SLACK_BOT_TOKEN")
	if tok == "" {
		return SlackConfig{}, fmt.Errorf("war_room: SLACK_BOT_TOKEN unset (provider creds via env only — fail closed)")
	}
	return SlackConfig{BotToken: tok}, nil
}

// slackProvider is the real ChannelProvider. V1 is a thin scaffold: the
// concrete Slack HTTP calls (conversations.create, conversations.invite,
// chat.postMessage) land when the live workspace is wired. The interface +
// fail-closed credential gate are the load-bearing pieces; unit + integration
// tests exercise the orchestration via a fake provider. The live round-trip
// is tracked as D-INCIDENT-LIVE-SMOKE.
type slackProvider struct {
	cfg SlackConfig
}

// NewSlackProvider builds the real provider. Requires a non-empty bot token.
func NewSlackProvider(cfg SlackConfig) (ChannelProvider, error) {
	if cfg.BotToken == "" {
		return nil, fmt.Errorf("war_room: refusing to build slack provider without bot token")
	}
	return &slackProvider{cfg: cfg}, nil
}

func (p *slackProvider) CreateChannel(ctx context.Context, name, topic string) (string, error) {
	return "", fmt.Errorf("war_room: live Slack conversations.create not wired (D-INCIDENT-LIVE-SMOKE); name=%s", name)
}

func (p *slackProvider) Invite(ctx context.Context, channelID string, userIDs []string) error {
	return fmt.Errorf("war_room: live Slack conversations.invite not wired (D-INCIDENT-LIVE-SMOKE)")
}

func (p *slackProvider) PostMessage(ctx context.Context, channelID, text string) error {
	return fmt.Errorf("war_room: live Slack chat.postMessage not wired (D-INCIDENT-LIVE-SMOKE)")
}
