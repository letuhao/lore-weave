//go:build integration

package integration

import (
	"os"
	"regexp"
	"strings"
	"testing"
)

// TestLogPipeline_VectorScrubberPatterns_RegexCoverage validates the
// L7.F.2 LOCKED pattern set is present in infra/vector/scrubber_patterns.yaml
// AND that infra/vector/vector.toml applies each pattern with a non-empty
// replacement.
//
// This is a CONTRACT-level test (runs in CI without infra) that pins the
// regex set so a future commit that silently drops a pattern is a visible
// test break.
//
// The full live ingest-replay test (start Vector + Loki via docker-compose,
// inject PII line, query Loki, assert scrubbed) ships V1+30d per
// D-VECTOR-LIVE-PIPELINE-SMOKE in DEFERRED.md.
func TestLogPipeline_VectorScrubberPatterns_RegexCoverage(t *testing.T) {
	patternsPath := "../../infra/vector/scrubber_patterns.yaml"
	raw, err := os.ReadFile(patternsPath)
	if err != nil {
		t.Fatalf("read scrubber_patterns.yaml: %v", err)
	}

	expectedPatternIDs := []string{
		"email",
		"phone",
		"ipv4",
		"ipv6",
		"cc_pan",
		"ssn_us",
		"api_key_like",
	}

	for _, id := range expectedPatternIDs {
		if !strings.Contains(string(raw), "id: "+id) {
			t.Errorf("scrubber_patterns.yaml missing pattern id: %s (L7.F.2 LOCKED set)", id)
		}
	}

	// Vector config must reference each pattern category in a replace call.
	vectorPath := "../../infra/vector/vector.toml"
	vraw, err := os.ReadFile(vectorPath)
	if err != nil {
		t.Fatalf("read vector.toml: %v", err)
	}
	requiredCalls := []string{
		`\*\*\*@\*\*\*\.\*\*\*`,
		`\*\*\*-PHONE-\*\*\*`,
		`\*\*\*\.\*\*\*\.\*\*\*\.\*\*\*`,
		`\*\*\*:IPV6:\*\*\*`,
		`\*\*\*-PAN-\*\*\*`,
		`\*\*\*-SSN-\*\*\*`,
		`\*\*\*-APIKEYLIKE-\*\*\*`,
	}
	for _, want := range requiredCalls {
		matched, _ := regexp.MatchString(want, string(vraw))
		if !matched {
			t.Errorf("vector.toml missing scrubber replacement matching: %s", want)
		}
	}
}

// TestLogPipeline_RetentionDefault30d — pins Loki retention at 30d
// (Q-L1I-2 alignment: logs match short-term Prom retention).
func TestLogPipeline_RetentionDefault30d(t *testing.T) {
	retentionPath := "../../infra/loki/retention.yaml"
	raw, err := os.ReadFile(retentionPath)
	if err != nil {
		t.Fatalf("read retention.yaml: %v", err)
	}
	if !strings.Contains(string(raw), "expected_default_retention_hours: 720") {
		t.Errorf("retention.yaml drift: expected_default_retention_hours must be 720 (30d)")
	}
	if !strings.Contains(string(raw), "retention_period: 720h") {
		t.Errorf("retention.yaml: default tenant retention_period must be 720h")
	}
}

// TestLogPipeline_LokiSelfHosted_NoManagedRefs — pin Q-L7F-1: foundation
// V1 = Loki self-hosted. Reject any Datadog / Splunk / managed-SaaS sink.
func TestLogPipeline_LokiSelfHosted_NoManagedRefs(t *testing.T) {
	vectorPath := "../../infra/vector/vector.toml"
	raw, err := os.ReadFile(vectorPath)
	if err != nil {
		t.Fatalf("read vector.toml: %v", err)
	}
	managedRefs := []string{
		`type = "datadog`,
		`type = "splunk`,
		`type = "elasticsearch`,
		`type = "newrelic`,
		`type = "honeycomb`,
	}
	for _, ref := range managedRefs {
		if strings.Contains(string(raw), ref) {
			t.Errorf("Q-L7F-1 violation: vector.toml references managed log SaaS sink: %s", ref)
		}
	}
}

// TestLogPipeline_LiveSmokeGate — placeholder for the live docker-compose
// pipeline smoke. Mirrors degraded_mode_test.go pattern.
func TestLogPipeline_LiveSmokeGate(t *testing.T) {
	if os.Getenv("LW_LOG_PIPELINE_LIVE_HARNESS") == "" {
		t.Skip("LW_LOG_PIPELINE_LIVE_HARNESS unset; running contract-level test only")
	}
	// Live path (V1+30d activation): bring up Vector + Loki, inject log with
	// PII, query Loki, assert PII is scrubbed at line content level.
	t.Skip("D-VECTOR-LIVE-PIPELINE-SMOKE — live harness ships V1+30d cycle")
}
