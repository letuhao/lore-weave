package dependencies

import (
	"errors"
	"fmt"
	"sync"
	"time"
)

// WrappedClientConfig is the resolved per-(service, dep) configuration
// returned by ClientFactory.For. Service code consumes this to wire its
// HTTP/DB/Redis client through the resilience primitives.
//
// We intentionally do NOT import contracts/resilience here — that would
// introduce a cross-package go-mod dep and force every consumer to pull
// the matrix loader into their build graph. Service code does the
// wiring locally:
//
//	cfg := matrix.For("my-service", "llm-anthropic")
//	bh, _ := resilience.NewBulkhead(resilience.BulkheadConfig{
//	    DepName: cfg.DepName, MaxConcurrent: cfg.BulkheadMaxConcurrent, …
//	})
//
// The factory's value is centralization of WHICH config to use for WHICH
// dep; the resilience package's value is the primitive implementation.
type WrappedClientConfig struct {
	// Service is the calling service (for the per-(caller_service, dep)
	// breaker-isolation rule per SR06 §12AI.4).
	Service string

	// DepName + Type + Criticality bubbled up from the matrix entry —
	// callers use these for metric labels + dispatch.
	DepName     string
	Type        DepType
	Criticality Criticality

	// Resilience primitive configuration.
	Timeout                     time.Duration
	BreakerErrorRateThreshold   float64
	BreakerMinRequests          int
	BreakerOpenDuration         time.Duration
	BreakerHalfOpenProbeInterval time.Duration
	RetryClass                  RetryClass
	BulkheadMaxConcurrent       int
	BulkheadQueueDepth          int
	BulkheadQueueTimeout        time.Duration

	// Fallback is the ordered fallback chain (already validated DAG-safe
	// by LoadAndValidate). Service code may use this for multi-provider
	// LLM failover per SR06 §12AI.7.
	Fallback []string

	// Runbook is the docs/sre/runbooks/… relative path. Service log lines
	// emitted on breaker-open / drain-trigger SHOULD include this so
	// on-call can jump straight to the playbook.
	Runbook string
}

// ErrServiceUnregistered is returned by ClientFactory.For when the caller
// service is not in the dep's owner_service or also_used_by list. This
// keeps the SR06 §12AI.2 "every caller declared" invariant honest at
// runtime — a service that copy-pasted code from another service won't
// silently inherit the wrapped client.
var ErrServiceUnregistered = errors.New("dependencies: service not registered as caller")

// ErrUnknownDep is returned by ClientFactory.For when depName is not
// in the matrix.
var ErrUnknownDep = errors.New("dependencies: unknown dependency")

// ClientFactory wraps a loaded Matrix + resolves per-(service, dep)
// configurations. Safe for concurrent use across goroutines (the matrix
// is immutable after LoadAndValidate).
type ClientFactory struct {
	mu     sync.RWMutex
	matrix Matrix
	// index: service -> dep -> resolved config (computed lazily).
	cache map[string]map[string]WrappedClientConfig
}

// NewClientFactory wraps the loaded matrix.
func NewClientFactory(m Matrix) *ClientFactory {
	return &ClientFactory{matrix: m, cache: make(map[string]map[string]WrappedClientConfig)}
}

// For returns the resolved per-(service, dep) configuration. service
// MUST appear in the dep's owner_service or also_used_by list; else
// ErrServiceUnregistered.
//
// The (service, dep) pair is cached after first computation — repeated
// calls are O(1) reads from the cache.
func (f *ClientFactory) For(service, depName string) (WrappedClientConfig, error) {
	if service == "" {
		return WrappedClientConfig{}, fmt.Errorf("%w: service empty", ErrServiceUnregistered)
	}
	f.mu.RLock()
	if perDep, ok := f.cache[service]; ok {
		if cfg, ok := perDep[depName]; ok {
			f.mu.RUnlock()
			return cfg, nil
		}
	}
	f.mu.RUnlock()

	dep, ok := f.matrix.Find(depName)
	if !ok {
		return WrappedClientConfig{}, fmt.Errorf("%w: %q", ErrUnknownDep, depName)
	}
	if !isRegisteredCaller(service, dep) {
		return WrappedClientConfig{}, fmt.Errorf("%w: service=%q dep=%q", ErrServiceUnregistered, service, depName)
	}
	cfg := resolveConfig(service, dep)

	f.mu.Lock()
	defer f.mu.Unlock()
	if _, ok := f.cache[service]; !ok {
		f.cache[service] = make(map[string]WrappedClientConfig)
	}
	f.cache[service][depName] = cfg
	return cfg, nil
}

// Matrix returns the underlying matrix; useful for callers that want
// to enumerate all registered deps (e.g., bootstrap-time pool sizing).
func (f *ClientFactory) Matrix() Matrix {
	return f.matrix
}

// isRegisteredCaller returns true if `service` is either the dep's
// owner_service OR appears in also_used_by. Case-sensitive match.
func isRegisteredCaller(service string, dep Dependency) bool {
	if service == dep.OwnerService {
		return true
	}
	for _, s := range dep.AlsoUsedBy {
		if s == service {
			return true
		}
	}
	return false
}

// resolveConfig translates a Dependency YAML entry into a usable
// WrappedClientConfig. Defaults: HalfOpenProbeInterval = 1s (matches
// resilience.NewBreaker default if zero).
func resolveConfig(service string, dep Dependency) WrappedClientConfig {
	return WrappedClientConfig{
		Service:                      service,
		DepName:                      dep.Name,
		Type:                         dep.Type,
		Criticality:                  dep.Criticality,
		Timeout:                      time.Duration(dep.TimeoutMS) * time.Millisecond,
		BreakerErrorRateThreshold:    dep.CircuitBreaker.ErrorRateThreshold,
		BreakerMinRequests:           dep.CircuitBreaker.MinRequests,
		BreakerOpenDuration:          time.Duration(dep.CircuitBreaker.OpenDurationMS) * time.Millisecond,
		BreakerHalfOpenProbeInterval: time.Second, // SR06 default; matrix can override later
		RetryClass:                   dep.RetryClass,
		BulkheadMaxConcurrent:        dep.Bulkhead.MaxConcurrent,
		BulkheadQueueDepth:           dep.Bulkhead.QueueDepth,
		BulkheadQueueTimeout:         time.Duration(dep.Bulkhead.QueueTimeoutMS) * time.Millisecond,
		Fallback:                     append([]string(nil), dep.Fallback...),
		Runbook:                      dep.Runbook,
	}
}
