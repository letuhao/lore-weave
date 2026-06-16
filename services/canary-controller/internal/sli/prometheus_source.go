// Package sli binds the controller's SLISource port to a Prometheus
// instant-query endpoint (D-CANARY-LIVE-WIRING / 064).
//
// V1 metric contract: lw_canary_sli_cohort{deploy_id,stage} — the cohort burn
// rate emitted by the deployed services. The precise stage-0 error-rate metric
// finalizes when real services emit cohort SLIs (D-CANARY-LIVE-SMOKE); until
// then the single series feeds both Observation fields (Decide() reads only the
// one relevant to the current stage, so this is exact for the state machine).
package sli

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/loreweave/foundation/services/canary-controller/internal/canary"
	"github.com/loreweave/foundation/services/canary-controller/internal/controller"
)

// Clock returns "now" for the Observation (injectable; never time.Now in tests).
type Clock func() time.Time

// PrometheusSource queries a Prometheus instant-query endpoint for the
// cohort-scoped SLI of a canary deploy.
type PrometheusSource struct {
	baseURL string
	client  *http.Client
	now     Clock
}

var _ controller.SLISource = (*PrometheusSource)(nil)

// NewPrometheusSource builds a source against promURL (e.g. http://prometheus:9090).
// A trailing slash is trimmed; now defaults to time.Now when nil.
func NewPrometheusSource(promURL string, now Clock) *PrometheusSource {
	if now == nil {
		now = time.Now
	}
	return &PrometheusSource{
		baseURL: strings.TrimRight(promURL, "/"),
		client:  &http.Client{Timeout: 10 * time.Second},
		now:     now,
	}
}

// buildQuery builds the PromQL instant query for a deploy at a stage.
//
// deployID is a deploy_audit UUID PK (migration 023: `deploy_id UUID PRIMARY
// KEY`), so it cannot contain PromQL-injection characters; %q-quoting is
// sufficient here. If deploy_id ever becomes free-text, this needs a real
// PromQL label-value escaper (incidental %q-escaping is not a guarantee).
func buildQuery(deployID string, stage canary.Stage) string {
	return fmt.Sprintf(`lw_canary_sli_cohort{deploy_id=%q,stage="%d"}`, deployID, int(stage))
}

// Observe queries Prometheus and returns the cohort burn / error rate.
func (s *PrometheusSource) Observe(ctx context.Context, deployID string, stage canary.Stage) (canary.Observation, error) {
	q := buildQuery(deployID, stage)
	endpoint := s.baseURL + "/api/v1/query?" + url.Values{"query": {q}}.Encode()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return canary.Observation{}, fmt.Errorf("sli: build request: %w", err)
	}
	resp, err := s.client.Do(req)
	if err != nil {
		return canary.Observation{}, fmt.Errorf("sli: query prometheus: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()
	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return canary.Observation{}, fmt.Errorf("sli: read body: %w", err)
	}
	val, err := parseInstantScalar(resp.StatusCode, body)
	if err != nil {
		return canary.Observation{}, err
	}
	// Decide() reads ErrorRate at stage 0 and CohortBurn at stages 1+; both are
	// populated from the single observed series (only the stage-relevant field
	// is consulted, so this is exact, not a fudge).
	return canary.Observation{CohortBurn: val, ErrorRate: val, Now: s.now()}, nil
}

// promResponse is the Prometheus instant-query envelope.
type promResponse struct {
	Status string `json:"status"`
	Data   struct {
		ResultType string `json:"resultType"`
		Result     []struct {
			Value [2]json.RawMessage `json:"value"` // [ <unix ts>, "<scalar string>" ]
		} `json:"result"`
	} `json:"data"`
	ErrorType string `json:"errorType"`
	Error     string `json:"error"`
}

// parseInstantScalar extracts the scalar value from a Prometheus instant-vector
// response. A non-200, a non-"success" status, or an EMPTY result is an error:
// a missing series must NOT silently read as 0 burn — that would mask a broken
// SLI pipeline as "healthy" and advance a canary blind.
func parseInstantScalar(status int, body []byte) (float64, error) {
	if status != http.StatusOK {
		return 0, fmt.Errorf("sli: prometheus status %d: %s", status, snippet(body))
	}
	var pr promResponse
	if err := json.Unmarshal(body, &pr); err != nil {
		return 0, fmt.Errorf("sli: decode response: %w", err)
	}
	if pr.Status != "success" {
		return 0, fmt.Errorf("sli: prometheus error %q: %s", pr.ErrorType, pr.Error)
	}
	if len(pr.Data.Result) == 0 {
		return 0, fmt.Errorf("sli: empty result (no cohort SLI series — pipeline not emitting?)")
	}
	var valStr string
	if err := json.Unmarshal(pr.Data.Result[0].Value[1], &valStr); err != nil {
		return 0, fmt.Errorf("sli: decode value: %w", err)
	}
	f, err := strconv.ParseFloat(valStr, 64)
	if err != nil {
		return 0, fmt.Errorf("sli: parse scalar %q: %w", valStr, err)
	}
	return f, nil
}

func snippet(b []byte) string {
	const max = 200
	if len(b) > max {
		return string(b[:max])
	}
	return string(b)
}
