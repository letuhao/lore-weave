package dependencies

import (
	"errors"
	"testing"
	"time"
)

func newTestMatrix() Matrix {
	return Matrix{
		Version: 1,
		Dependencies: []Dependency{
			{
				Name: "llm-anthropic", OwnerService: "roleplay-service",
				AlsoUsedBy:  []string{"chat-service"},
				Criticality: CriticalityP1, Type: DepTypeHTTPExternal,
				SLATarget: "99.5%", TimeoutMS: 60000,
				CircuitBreaker: BreakerYAML{ErrorRateThreshold: 0.25, MinRequests: 20, OpenDurationMS: 30000},
				RetryClass:     RetryClassNonIdempotent,
				Bulkhead:       BulkheadYAML{MaxConcurrent: 30, QueueDepth: 15, QueueTimeoutMS: 200},
				Fallback:       []string{"llm-openai"},
				Runbook:        "runbook.md",
			},
			{
				Name: "llm-openai", OwnerService: "roleplay-service",
				Criticality: CriticalityP1, Type: DepTypeHTTPExternal,
				SLATarget: "99.5%", TimeoutMS: 60000,
				CircuitBreaker: BreakerYAML{ErrorRateThreshold: 0.25, MinRequests: 20, OpenDurationMS: 30000},
				RetryClass:     RetryClassNonIdempotent,
				Bulkhead:       BulkheadYAML{MaxConcurrent: 30, QueueDepth: 15, QueueTimeoutMS: 200},
				Fallback:       []string{},
				Runbook:        "runbook2.md",
			},
		},
	}
}

func TestClientFactory_For_HappyPath(t *testing.T) {
	f := NewClientFactory(newTestMatrix())
	cfg, err := f.For("roleplay-service", "llm-anthropic")
	if err != nil {
		t.Fatalf("err = %v", err)
	}
	if cfg.Service != "roleplay-service" || cfg.DepName != "llm-anthropic" {
		t.Errorf("fields wrong: %+v", cfg)
	}
	if cfg.Timeout != 60*time.Second {
		t.Errorf("Timeout = %v, want 60s", cfg.Timeout)
	}
	if cfg.BulkheadMaxConcurrent != 30 {
		t.Errorf("BulkheadMaxConcurrent = %d, want 30", cfg.BulkheadMaxConcurrent)
	}
	if len(cfg.Fallback) != 1 || cfg.Fallback[0] != "llm-openai" {
		t.Errorf("Fallback = %v, want [llm-openai]", cfg.Fallback)
	}
}

func TestClientFactory_For_AlsoUsedByAccepted(t *testing.T) {
	f := NewClientFactory(newTestMatrix())
	cfg, err := f.For("chat-service", "llm-anthropic")
	if err != nil {
		t.Errorf("also_used_by caller should be accepted; err=%v", err)
	}
	if cfg.Service != "chat-service" {
		t.Errorf("Service = %q, want chat-service", cfg.Service)
	}
}

func TestClientFactory_For_RejectsUnregisteredService(t *testing.T) {
	f := NewClientFactory(newTestMatrix())
	_, err := f.For("rogue-service", "llm-anthropic")
	if !errors.Is(err, ErrServiceUnregistered) {
		t.Errorf("err = %v, want ErrServiceUnregistered", err)
	}
}

func TestClientFactory_For_RejectsEmptyService(t *testing.T) {
	f := NewClientFactory(newTestMatrix())
	_, err := f.For("", "llm-anthropic")
	if !errors.Is(err, ErrServiceUnregistered) {
		t.Errorf("err = %v, want ErrServiceUnregistered", err)
	}
}

func TestClientFactory_For_RejectsUnknownDep(t *testing.T) {
	f := NewClientFactory(newTestMatrix())
	_, err := f.For("roleplay-service", "ghost-dep")
	if !errors.Is(err, ErrUnknownDep) {
		t.Errorf("err = %v, want ErrUnknownDep", err)
	}
}

func TestClientFactory_For_CachesRepeatedCalls(t *testing.T) {
	f := NewClientFactory(newTestMatrix())
	c1, _ := f.For("roleplay-service", "llm-anthropic")
	c2, _ := f.For("roleplay-service", "llm-anthropic")
	// Fields equal (snapshot equality; not pointer-identity since copies).
	if c1.Service != c2.Service || c1.DepName != c2.DepName || c1.Timeout != c2.Timeout {
		t.Errorf("cached call returned different config")
	}
}

func TestClientFactory_Matrix_Exposed(t *testing.T) {
	f := NewClientFactory(newTestMatrix())
	if len(f.Matrix().Dependencies) != 2 {
		t.Errorf("Matrix() exposure lost deps")
	}
}
