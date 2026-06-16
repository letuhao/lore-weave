// Package pager binds the controller's Pager port to the PagerDuty Events API
// v2 (064; the cycle-35 PD escalation). PageSRE triggers an incident on a
// canary auto-abort (§12AH.4 "automatic rollback + SRE paged").
package pager

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/loreweave/foundation/services/canary-controller/internal/controller"
)

// PagerDutyPager pages SRE via the PagerDuty Events API v2.
type PagerDutyPager struct {
	baseURL    string // default https://events.pagerduty.com
	routingKey string
	client     *http.Client
}

var _ controller.Pager = (*PagerDutyPager)(nil)

// NewPagerDutyPager builds the pager from an Events API v2 routing key.
// baseURL defaults to the public PagerDuty endpoint (overridable for tests).
func NewPagerDutyPager(baseURL, routingKey string) *PagerDutyPager {
	if baseURL == "" {
		baseURL = "https://events.pagerduty.com"
	}
	return &PagerDutyPager{
		baseURL:    strings.TrimRight(baseURL, "/"),
		routingKey: routingKey,
		client:     &http.Client{Timeout: 15 * time.Second},
	}
}

// pagerEvent is the PagerDuty Events API v2 trigger payload.
type pagerEvent struct {
	RoutingKey  string       `json:"routing_key"`
	EventAction string       `json:"event_action"`
	DedupKey    string       `json:"dedup_key,omitempty"`
	Payload     pagerPayload `json:"payload"`
}

type pagerPayload struct {
	Summary       string         `json:"summary"`
	Source        string         `json:"source"`
	Severity      string         `json:"severity"`
	CustomDetails map[string]any `json:"custom_details,omitempty"`
}

func buildEventBody(routingKey, deployID, reason string) ([]byte, error) {
	ev := pagerEvent{
		RoutingKey:  routingKey,
		EventAction: "trigger",
		// dedup by deploy so a flapping abort coalesces into one incident.
		DedupKey: "canary-abort:" + deployID,
		Payload: pagerPayload{
			Summary:  fmt.Sprintf("canary auto-abort: deploy %s — %s", deployID, reason),
			Source:   "canary-controller",
			Severity: "critical",
			CustomDetails: map[string]any{
				"deploy_id": deployID,
				"reason":    reason,
			},
		},
	}
	return json.Marshal(ev)
}

// PageSRE triggers a PagerDuty incident for a canary auto-abort.
func (p *PagerDutyPager) PageSRE(ctx context.Context, deployID, reason string) error {
	body, err := buildEventBody(p.routingKey, deployID, reason)
	if err != nil {
		return fmt.Errorf("pager: marshal event: %w", err)
	}
	endpoint := p.baseURL + "/v2/enqueue"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("pager: build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := p.client.Do(req)
	if err != nil {
		return fmt.Errorf("pager: enqueue: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()
	// Events API v2 returns 202 Accepted on success.
	if resp.StatusCode != http.StatusAccepted {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return fmt.Errorf("pager: pagerduty status %d: %s", resp.StatusCode, string(b))
	}
	return nil
}
