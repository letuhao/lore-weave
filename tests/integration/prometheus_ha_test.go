//go:build integration

package integration

import (
	"os"
	"strings"
	"testing"
)

// TestPrometheusHA_MainConfig_FederationAndExternalLabels validates the
// L7.H.1 LOCKED set: HA pair via federation (Q-L1I-1) means
//
//	(a) Each replica carries a `prom_replica` external_label.
//	(b) Each replica scrapes the OTHER's /federate endpoint (peer probe).
//	(c) Thanos receive endpoint commented out (Q-L1I-2 V1+30d).
//
// Pure CONTRACT test (no docker required). Live kill-one-replica smoke
// runs in scripts/raid/degraded-live-smoke.sh under the LW_DEGRADED_LIVE_HARNESS
// gate (D-DEGRADED-LIVE-SMOKE addressed cycle 33).
func TestPrometheusHA_MainConfig_FederationAndExternalLabels(t *testing.T) {
	mainPath := "../../infra/prometheus/main.yaml"
	raw, err := os.ReadFile(mainPath)
	if err != nil {
		t.Fatalf("read main.yaml: %v", err)
	}
	s := string(raw)

	// (a) prom_replica external label
	if !strings.Contains(s, "prom_replica:") {
		t.Errorf("main.yaml missing prom_replica external_label (Q-L1I-1 HA pair marker)")
	}
	if !strings.Contains(s, "${PROM_REPLICA_ID}") {
		t.Errorf("main.yaml prom_replica must be templated via PROM_REPLICA_ID env var")
	}

	// (b) prom-ha-peer scrape job for federation kill-one-replica
	if !strings.Contains(s, "job_name: prom-ha-peer") {
		t.Errorf("main.yaml missing prom-ha-peer scrape job (kill-one-replica visualization)")
	}
	if !strings.Contains(s, "metrics_path: /federate") {
		t.Errorf("main.yaml prom-ha-peer must use /federate metrics_path")
	}
	if !strings.Contains(s, "honor_labels: true") {
		t.Errorf("main.yaml federation must honor peer's external_labels")
	}

	// (c) remote_write Thanos block must be COMMENTED OUT (Q-L1I-2 V1 stub)
	if strings.Contains(s, "\nremote_write:\n  - url: http://thanos-receive") {
		t.Errorf("Q-L1I-2 violation: remote_write to Thanos is ACTIVE; V1 must be stubbed (commented)")
	}
	// Positive assertion: the commented stanza is present (intentional ship)
	if !strings.Contains(s, "# remote_write:") {
		t.Errorf("main.yaml: Thanos remote_write stanza missing (must be present + commented for V1+30d activation)")
	}
}

// TestPrometheusHA_RecordingRules_AggregationGroups — pins the 5 recording-
// rule groups shipped cycle 33. A future commit that drops or renames a
// group breaks dashboards (which query the recorded series).
func TestPrometheusHA_RecordingRules_AggregationGroups(t *testing.T) {
	rulesPath := "../../infra/prometheus/recording-rules/aggregation.yaml"
	raw, err := os.ReadFile(rulesPath)
	if err != nil {
		t.Fatalf("read aggregation.yaml: %v", err)
	}
	s := string(raw)

	expectedGroups := []string{
		"name: per_shard_health",
		"name: per_status_rate",
		"name: per_deploy_cohort",
		"name: per_tier",
		"name: observability_self",
	}
	for _, g := range expectedGroups {
		if !strings.Contains(s, g) {
			t.Errorf("aggregation.yaml missing rule group: %s", g)
		}
	}

	expectedRecords := []string{
		"lw:postgres_up:by_shard",
		"lw:postgres_xact_rate:by_shard",
		"lw:postgres_connections:by_shard",
		"lw:http_request_rate:by_service_status",
		"lw:http_error_ratio:by_service",
		"lw:deploy_cohort_health:ratio",
		"lw:request_rate:by_tier",
		"lw:request_latency_p95:by_tier",
		"lw:obs_stack_up",
		"lw:vector_events_per_sec",
		"lw:loki_ingestion_rate_bytes",
	}
	for _, r := range expectedRecords {
		if !strings.Contains(s, r) {
			t.Errorf("aggregation.yaml missing record: %s", r)
		}
	}
}

// TestPrometheusHA_ThanosStubbed — Q-L1I-2: Thanos sidecar STUBBED V1.
//
//	(a) STUB_FLAG.md exists with STATUS banner.
//	(b) thanos.yaml exists with guard.status: STUBBED_V1.
//	(c) docker-compose.observability.yml does NOT include `thanos-sidecar` as live service.
func TestPrometheusHA_ThanosStubbed(t *testing.T) {
	stubPath := "../../infra/thanos/STUB_FLAG.md"
	if _, err := os.Stat(stubPath); os.IsNotExist(err) {
		t.Fatalf("infra/thanos/STUB_FLAG.md missing — Q-L1I-2 stub marker required")
	}
	raw, err := os.ReadFile(stubPath)
	if err != nil {
		t.Fatalf("read STUB_FLAG.md: %v", err)
	}
	if !strings.Contains(string(raw), "STATUS:** STUBBED V1") {
		t.Errorf("STUB_FLAG.md missing 'STATUS: STUBBED V1' banner")
	}

	thanosPath := "../../infra/thanos/thanos.yaml"
	traw, err := os.ReadFile(thanosPath)
	if err != nil {
		t.Fatalf("read thanos.yaml: %v", err)
	}
	if !strings.Contains(string(traw), "STUBBED_V1") {
		t.Errorf("thanos.yaml missing guard.status: STUBBED_V1")
	}

	// Docker-compose check: thanos-sidecar must NOT be a service block.
	composePath := "../../infra/docker-compose.observability.yml"
	if _, err := os.Stat(composePath); err == nil {
		craw, _ := os.ReadFile(composePath)
		// Reject the canonical service block patterns
		if strings.Contains(string(craw), "thanos-sidecar:\n    image:") {
			t.Errorf("Q-L1I-2 violation: docker-compose.observability.yml has live thanos-sidecar service")
		}
		if strings.Contains(string(craw), "thanos-query:\n    image:") {
			t.Errorf("Q-L1I-2 violation: docker-compose.observability.yml has live thanos-query service")
		}
	}
}

// TestPrometheusHA_GrafanaDatasources_StandardUIDs — pin the LOCKED UID set.
func TestPrometheusHA_GrafanaDatasources_StandardUIDs(t *testing.T) {
	dsPath := "../../infra/grafana/provisioning/datasources/datasources.yaml"
	raw, err := os.ReadFile(dsPath)
	if err != nil {
		t.Fatalf("read datasources.yaml: %v", err)
	}
	s := string(raw)
	expected := []string{
		"uid: prom-primary",
		"uid: prom-secondary",
		"uid: loki-primary",
		"uid: thanos-query",
	}
	for _, want := range expected {
		if !strings.Contains(s, want) {
			t.Errorf("datasources.yaml missing %s (LOCKED cycle 33 UID set)", want)
		}
	}
	// thanos-query datasource must carry the stubbed marker
	if !strings.Contains(s, "lw_thanos_stubbed=true") {
		t.Errorf("thanos-query datasource missing lw_thanos_stubbed=true marker")
	}
}

// TestPrometheusHA_NoServiceMesh — Q-L7-3 carry-forward: no Istio / Linkerd / Envoy.
//
// Only checks NON-COMMENT lines. Comment lines that mention the Q-L7-3
// decision text (e.g. "NO service mesh — no Istio / Linkerd / Envoy") are
// LEGITIMATE; the check is for actual `image:` / `container_name:` /
// `service:` directives referencing mesh components.
func TestPrometheusHA_NoServiceMesh(t *testing.T) {
	composePath := "../../infra/docker-compose.observability.yml"
	if _, err := os.Stat(composePath); os.IsNotExist(err) {
		t.Skip("docker-compose.observability.yml not yet present (skipping mesh check)")
	}
	raw, err := os.ReadFile(composePath)
	if err != nil {
		t.Fatalf("read compose file: %v", err)
	}
	meshTokens := []string{"istio", "linkerd", "envoy", "consul-connect"}
	for _, line := range strings.Split(string(raw), "\n") {
		trim := strings.TrimSpace(line)
		if strings.HasPrefix(trim, "#") || trim == "" {
			continue
		}
		// Match only YAML directives that introduce a service / container /
		// image — never just any mention of the word.
		lower := strings.ToLower(trim)
		hasDirective := strings.HasPrefix(lower, "image:") ||
			strings.HasPrefix(lower, "container_name:") ||
			strings.HasPrefix(lower, "hostname:") ||
			(strings.HasSuffix(lower, ":") && !strings.Contains(lower, " "))
		if !hasDirective {
			continue
		}
		for _, tok := range meshTokens {
			if strings.Contains(lower, tok) {
				t.Errorf("Q-L7-3 violation: observability docker-compose line %q references mesh token %q", trim, tok)
			}
		}
	}
}
