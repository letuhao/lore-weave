// Package executor binds the controller's RolloutExecutor port to GitHub
// Actions repository_dispatch (Q-L7K-1 GitHub Actions V1 / 064). Promote +
// Rollback send a typed dispatch event; the workflow that consumes it and
// performs the actual ECS/k8s traffic shift is wired with the deploy tooling
// (D-CANARY-LIVE-SMOKE / D-DEPLOY-LIVE-WIRING / 063).
package executor

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/loreweave/foundation/services/canary-controller/internal/canary"
	"github.com/loreweave/foundation/services/canary-controller/internal/controller"
)

const (
	eventPromote  = "canary-promote"
	eventRollback = "canary-rollback"
)

// GitHubExecutor performs the traffic shift / rollback by POSTing a
// repository_dispatch event to GitHub Actions.
type GitHubExecutor struct {
	baseURL string // default https://api.github.com
	owner   string
	repo    string
	token   string
	client  *http.Client
}

var _ controller.RolloutExecutor = (*GitHubExecutor)(nil)

// NewGitHubExecutor builds the executor. repoSlug is "owner/repo"; baseURL
// defaults to the public GitHub API (overridable for tests).
func NewGitHubExecutor(baseURL, repoSlug, token string) (*GitHubExecutor, error) {
	owner, repo, ok := strings.Cut(repoSlug, "/")
	if !ok || owner == "" || repo == "" {
		return nil, fmt.Errorf("executor: GITHUB_REPO must be \"owner/repo\", got %q", repoSlug)
	}
	if token == "" {
		return nil, fmt.Errorf("executor: GITHUB_TOKEN is empty")
	}
	if baseURL == "" {
		baseURL = "https://api.github.com"
	}
	return &GitHubExecutor{
		baseURL: strings.TrimRight(baseURL, "/"),
		owner:   owner,
		repo:    repo,
		token:   token,
		client:  &http.Client{Timeout: 15 * time.Second},
	}, nil
}

// dispatchBody is the repository_dispatch payload.
type dispatchBody struct {
	EventType     string         `json:"event_type"`
	ClientPayload map[string]any `json:"client_payload"`
}

func buildDispatchBody(eventType string, payload map[string]any) ([]byte, error) {
	return json.Marshal(dispatchBody{EventType: eventType, ClientPayload: payload})
}

// Promote shifts traffic so the given stage's cohorts run the new code.
func (e *GitHubExecutor) Promote(ctx context.Context, deployID string, to canary.Stage) error {
	return e.dispatch(ctx, eventPromote, map[string]any{
		"deploy_id": deployID,
		"stage":     int(to),
	})
}

// Rollback reverts ALL cohorts to the prior version.
func (e *GitHubExecutor) Rollback(ctx context.Context, deployID, reason string) error {
	return e.dispatch(ctx, eventRollback, map[string]any{
		"deploy_id": deployID,
		"reason":    reason,
	})
}

func (e *GitHubExecutor) dispatch(ctx context.Context, eventType string, payload map[string]any) error {
	body, err := buildDispatchBody(eventType, payload)
	if err != nil {
		return fmt.Errorf("executor: marshal %s: %w", eventType, err)
	}
	endpoint := fmt.Sprintf("%s/repos/%s/%s/dispatches", e.baseURL, e.owner, e.repo)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("executor: build request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+e.token)
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("Content-Type", "application/json")
	resp, err := e.client.Do(req)
	if err != nil {
		return fmt.Errorf("executor: dispatch %s: %w", eventType, err)
	}
	defer func() { _ = resp.Body.Close() }()
	// repository_dispatch returns 204 No Content on success.
	if resp.StatusCode != http.StatusNoContent {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return fmt.Errorf("executor: dispatch %s: github status %d: %s", eventType, resp.StatusCode, string(b))
	}
	return nil
}
