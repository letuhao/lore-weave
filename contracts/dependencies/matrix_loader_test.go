package dependencies

import (
	"errors"
	"path/filepath"
	"runtime"
	"testing"
)

// TestLoadAndValidate_RealMatrixYAML pins that the shipped matrix.yaml
// parses + validates + is DAG-safe. The cycle-18 verify script invokes
// this test to gate the CYCLE_LOG row.
func TestLoadAndValidate_RealMatrixYAML(t *testing.T) {
	_, thisFile, _, _ := runtime.Caller(0)
	matrixPath := filepath.Join(filepath.Dir(thisFile), "matrix.yaml")
	m, err := LoadAndValidate(matrixPath)
	if err != nil {
		t.Fatalf("LoadAndValidate(%s): %v", matrixPath, err)
	}
	if m.Version != 1 {
		t.Errorf("Version = %d, want 1", m.Version)
	}
	if len(m.Dependencies) < 5 {
		t.Errorf("expected at least 5 deps in shipped matrix; got %d", len(m.Dependencies))
	}
	// Spot-check critical entries exist.
	mustFind := []string{"meta-db", "auth-service", "redis-streams", "llm-anthropic", "minio"}
	for _, n := range mustFind {
		if _, ok := m.Find(n); !ok {
			t.Errorf("matrix missing dep %q", n)
		}
	}
}

func TestParseAndValidate_RejectsUnsupportedVersion(t *testing.T) {
	bad := []byte(`
version: 99
dependencies: []
`)
	_, err := ParseAndValidate(bad)
	if err == nil || !contains(err.Error(), "unsupported matrix version") {
		t.Errorf("err = %v, want unsupported version error", err)
	}
}

func TestParseAndValidate_RejectsDuplicateName(t *testing.T) {
	bad := []byte(`
version: 1
dependencies:
  - name: dup
    owner_service: s
    criticality: P1
    type: http_external
    sla_target: "99.9%"
    timeout_ms: 1000
    circuit_breaker:
      error_rate_threshold: 0.25
      min_requests: 10
      open_duration_ms: 1000
    retry_class: idempotent
    bulkhead:
      max_concurrent: 5
      queue_depth: 2
      queue_timeout_ms: 100
    fallback: []
    degraded_modes: []
    runbook: r.md
  - name: dup
    owner_service: s
    criticality: P1
    type: http_external
    sla_target: "99.9%"
    timeout_ms: 1000
    circuit_breaker:
      error_rate_threshold: 0.25
      min_requests: 10
      open_duration_ms: 1000
    retry_class: idempotent
    bulkhead:
      max_concurrent: 5
      queue_depth: 2
      queue_timeout_ms: 100
    fallback: []
    degraded_modes: []
    runbook: r.md
`)
	_, err := ParseAndValidate(bad)
	if !errors.Is(err, ErrDuplicateDependency) {
		t.Errorf("err = %v, want ErrDuplicateDependency", err)
	}
}

func TestParseAndValidate_RejectsUnknownFallback(t *testing.T) {
	bad := []byte(`
version: 1
dependencies:
  - name: a
    owner_service: s
    criticality: P1
    type: http_external
    sla_target: "99.9%"
    timeout_ms: 1000
    circuit_breaker:
      error_rate_threshold: 0.25
      min_requests: 10
      open_duration_ms: 1000
    retry_class: idempotent
    bulkhead:
      max_concurrent: 5
      queue_depth: 2
      queue_timeout_ms: 100
    fallback: [nonexistent]
    degraded_modes: []
    runbook: r.md
`)
	_, err := ParseAndValidate(bad)
	if !errors.Is(err, ErrUnknownFallback) {
		t.Errorf("err = %v, want ErrUnknownFallback", err)
	}
}

// TestParseAndValidate_RejectsFallbackCycle is the load-bearing DAG test.
// A cycle in the fallback graph would cause unbounded failover loops in
// client_factory.go — LoadAndValidate MUST refuse to load.
func TestParseAndValidate_RejectsFallbackCycle(t *testing.T) {
	cyclic := []byte(`
version: 1
dependencies:
  - name: llm-a
    owner_service: s
    criticality: P1
    type: http_external
    sla_target: "99.9%"
    timeout_ms: 1000
    circuit_breaker:
      error_rate_threshold: 0.25
      min_requests: 10
      open_duration_ms: 1000
    retry_class: non_idempotent
    bulkhead:
      max_concurrent: 5
      queue_depth: 2
      queue_timeout_ms: 100
    fallback: [llm-b]
    degraded_modes: []
    runbook: r.md
  - name: llm-b
    owner_service: s
    criticality: P1
    type: http_external
    sla_target: "99.9%"
    timeout_ms: 1000
    circuit_breaker:
      error_rate_threshold: 0.25
      min_requests: 10
      open_duration_ms: 1000
    retry_class: non_idempotent
    bulkhead:
      max_concurrent: 5
      queue_depth: 2
      queue_timeout_ms: 100
    fallback: [llm-c]
    degraded_modes: []
    runbook: r.md
  - name: llm-c
    owner_service: s
    criticality: P1
    type: http_external
    sla_target: "99.9%"
    timeout_ms: 1000
    circuit_breaker:
      error_rate_threshold: 0.25
      min_requests: 10
      open_duration_ms: 1000
    retry_class: non_idempotent
    bulkhead:
      max_concurrent: 5
      queue_depth: 2
      queue_timeout_ms: 100
    fallback: [llm-a]
    degraded_modes: []
    runbook: r.md
`)
	_, err := ParseAndValidate(cyclic)
	if !errors.Is(err, ErrFallbackCycle) {
		t.Errorf("err = %v, want ErrFallbackCycle (a→b→c→a)", err)
	}
}

func TestParseAndValidate_AcceptsLinearFallbackChain(t *testing.T) {
	// a → b → c (no cycle) — must load cleanly.
	good := []byte(`
version: 1
dependencies:
  - name: a
    owner_service: s
    criticality: P1
    type: http_external
    sla_target: "99.9%"
    timeout_ms: 1000
    circuit_breaker:
      error_rate_threshold: 0.25
      min_requests: 10
      open_duration_ms: 1000
    retry_class: non_idempotent
    bulkhead:
      max_concurrent: 5
      queue_depth: 2
      queue_timeout_ms: 100
    fallback: [b]
    degraded_modes: []
    runbook: r.md
  - name: b
    owner_service: s
    criticality: P1
    type: http_external
    sla_target: "99.9%"
    timeout_ms: 1000
    circuit_breaker:
      error_rate_threshold: 0.25
      min_requests: 10
      open_duration_ms: 1000
    retry_class: non_idempotent
    bulkhead:
      max_concurrent: 5
      queue_depth: 2
      queue_timeout_ms: 100
    fallback: [c]
    degraded_modes: []
    runbook: r.md
  - name: c
    owner_service: s
    criticality: P1
    type: http_external
    sla_target: "99.9%"
    timeout_ms: 1000
    circuit_breaker:
      error_rate_threshold: 0.25
      min_requests: 10
      open_duration_ms: 1000
    retry_class: non_idempotent
    bulkhead:
      max_concurrent: 5
      queue_depth: 2
      queue_timeout_ms: 100
    fallback: []
    degraded_modes: []
    runbook: r.md
`)
	m, err := ParseAndValidate(good)
	if err != nil {
		t.Fatalf("err = %v, want nil for linear chain", err)
	}
	if len(m.Dependencies) != 3 {
		t.Errorf("got %d deps, want 3", len(m.Dependencies))
	}
}

func TestDependency_Validate_RejectsBadFields(t *testing.T) {
	base := Dependency{
		Name:         "d",
		OwnerService: "s",
		Criticality:  CriticalityP1,
		Type:         DepTypeHTTPExternal,
		SLATarget:    "99%",
		TimeoutMS:    1000,
		CircuitBreaker: BreakerYAML{
			ErrorRateThreshold: 0.25, MinRequests: 10, OpenDurationMS: 1000,
		},
		RetryClass: RetryClassIdempotent,
		Bulkhead:   BulkheadYAML{MaxConcurrent: 5, QueueDepth: 2, QueueTimeoutMS: 100},
		Runbook:    "r.md",
	}
	cases := []struct {
		name   string
		mutate func(*Dependency)
	}{
		{"empty name", func(d *Dependency) { d.Name = "" }},
		{"empty owner", func(d *Dependency) { d.OwnerService = "" }},
		{"bad criticality", func(d *Dependency) { d.Criticality = "P99" }},
		{"bad type", func(d *Dependency) { d.Type = "smtp" }},
		{"zero timeout (SR06 I16)", func(d *Dependency) { d.TimeoutMS = 0 }},
		{"breaker threshold 0", func(d *Dependency) { d.CircuitBreaker.ErrorRateThreshold = 0 }},
		{"breaker threshold > 1", func(d *Dependency) { d.CircuitBreaker.ErrorRateThreshold = 1.5 }},
		{"breaker min_requests 0", func(d *Dependency) { d.CircuitBreaker.MinRequests = 0 }},
		{"breaker open_duration 0", func(d *Dependency) { d.CircuitBreaker.OpenDurationMS = 0 }},
		{"unknown retry class", func(d *Dependency) { d.RetryClass = "yolo" }},
		{"bulkhead max_concurrent 0", func(d *Dependency) { d.Bulkhead.MaxConcurrent = 0 }},
		{"empty runbook", func(d *Dependency) { d.Runbook = "" }},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			d := base
			c.mutate(&d)
			err := d.Validate()
			if !errors.Is(err, ErrInvalidDependency) {
				t.Errorf("err = %v, want ErrInvalidDependency", err)
			}
		})
	}
}

func contains(haystack, needle string) bool {
	for i := 0; i+len(needle) <= len(haystack); i++ {
		if haystack[i:i+len(needle)] == needle {
			return true
		}
	}
	return false
}
