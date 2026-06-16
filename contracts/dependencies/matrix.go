package dependencies

import (
	"errors"
	"fmt"
)

// Criticality is the P0/P1/P2 tier from SR06 §12AI.2.
type Criticality string

const (
	// CriticalityP0 — platform-critical. Failure = full outage. Example: meta DB.
	CriticalityP0 Criticality = "P0"
	// CriticalityP1 — feature-critical. Failure degrades one feature. Example: LLM provider.
	CriticalityP1 Criticality = "P1"
	// CriticalityP2 — background. Failure doesn't block active play. Example: MinIO.
	CriticalityP2 Criticality = "P2"
)

// DepType is the transport kind for matrix routing decisions.
type DepType string

const (
	DepTypeHTTPExternal DepType = "http_external"
	DepTypeHTTPInternal DepType = "http_internal"
	DepTypePostgres     DepType = "postgres"
	DepTypeRedis        DepType = "redis"
	DepTypeS3           DepType = "s3"
	DepTypeGRPC         DepType = "grpc"
)

// RetryClass mirrors the resilience package enum but as the YAML
// string form. matrix_loader converts to resilience.RetryClass at
// client_factory wiring time (avoids a cross-package go-mod dep here).
type RetryClass string

const (
	RetryClassIdempotent    RetryClass = "idempotent"
	RetryClassNonIdempotent RetryClass = "non_idempotent"
	RetryClassCriticalWrite RetryClass = "critical_write"
)

// BreakerYAML mirrors the matrix.yaml circuit_breaker block.
type BreakerYAML struct {
	ErrorRateThreshold float64 `yaml:"error_rate_threshold"`
	MinRequests        int     `yaml:"min_requests"`
	OpenDurationMS     int     `yaml:"open_duration_ms"`
}

// BulkheadYAML mirrors the matrix.yaml bulkhead block.
type BulkheadYAML struct {
	MaxConcurrent  int `yaml:"max_concurrent"`
	QueueDepth     int `yaml:"queue_depth"`
	QueueTimeoutMS int `yaml:"queue_timeout_ms"`
}

// Dependency is one matrix.yaml entry.
type Dependency struct {
	Name           string       `yaml:"name"`
	OwnerService   string       `yaml:"owner_service"`
	AlsoUsedBy     []string     `yaml:"also_used_by"`
	Criticality    Criticality  `yaml:"criticality"`
	Type           DepType      `yaml:"type"`
	SLATarget      string       `yaml:"sla_target"`
	TimeoutMS      int          `yaml:"timeout_ms"`
	CircuitBreaker BreakerYAML  `yaml:"circuit_breaker"`
	RetryClass     RetryClass   `yaml:"retry_class"`
	Bulkhead       BulkheadYAML `yaml:"bulkhead"`
	Fallback       []string     `yaml:"fallback"`
	DegradedModes  []string     `yaml:"degraded_modes"`
	Runbook        string       `yaml:"runbook"`
}

// Matrix is the loaded top-level structure.
type Matrix struct {
	Version      int          `yaml:"version"`
	Dependencies []Dependency `yaml:"dependencies"`
}

// Validate inspects a Dependency for required fields + sane values.
// Called by LoadAndValidate per dep; exposed for ad-hoc programmatic
// construction (e.g., test fixtures).
func (d Dependency) Validate() error {
	if d.Name == "" {
		return fmt.Errorf("%w: name empty", ErrInvalidDependency)
	}
	if d.OwnerService == "" {
		return fmt.Errorf("%w: dep=%q owner_service empty", ErrInvalidDependency, d.Name)
	}
	switch d.Criticality {
	case CriticalityP0, CriticalityP1, CriticalityP2:
	default:
		return fmt.Errorf("%w: dep=%q criticality=%q (expected P0/P1/P2)", ErrInvalidDependency, d.Name, d.Criticality)
	}
	switch d.Type {
	case DepTypeHTTPExternal, DepTypeHTTPInternal, DepTypePostgres, DepTypeRedis, DepTypeS3, DepTypeGRPC:
	default:
		return fmt.Errorf("%w: dep=%q type=%q unknown", ErrInvalidDependency, d.Name, d.Type)
	}
	if d.TimeoutMS <= 0 {
		return fmt.Errorf("%w: dep=%q timeout_ms must be > 0 (SR06 I16)", ErrInvalidDependency, d.Name)
	}
	if d.CircuitBreaker.ErrorRateThreshold <= 0 || d.CircuitBreaker.ErrorRateThreshold > 1 {
		return fmt.Errorf("%w: dep=%q error_rate_threshold=%v must be in (0, 1]", ErrInvalidDependency, d.Name, d.CircuitBreaker.ErrorRateThreshold)
	}
	if d.CircuitBreaker.MinRequests <= 0 {
		return fmt.Errorf("%w: dep=%q min_requests must be > 0", ErrInvalidDependency, d.Name)
	}
	if d.CircuitBreaker.OpenDurationMS <= 0 {
		return fmt.Errorf("%w: dep=%q open_duration_ms must be > 0", ErrInvalidDependency, d.Name)
	}
	switch d.RetryClass {
	case RetryClassIdempotent, RetryClassNonIdempotent, RetryClassCriticalWrite:
	default:
		return fmt.Errorf("%w: dep=%q retry_class=%q unknown", ErrInvalidDependency, d.Name, d.RetryClass)
	}
	if d.Bulkhead.MaxConcurrent <= 0 {
		return fmt.Errorf("%w: dep=%q bulkhead.max_concurrent must be > 0", ErrInvalidDependency, d.Name)
	}
	if d.Bulkhead.QueueDepth < 0 {
		return fmt.Errorf("%w: dep=%q bulkhead.queue_depth must be >= 0", ErrInvalidDependency, d.Name)
	}
	if d.Bulkhead.QueueTimeoutMS < 0 {
		return fmt.Errorf("%w: dep=%q bulkhead.queue_timeout_ms must be >= 0", ErrInvalidDependency, d.Name)
	}
	if d.Runbook == "" {
		return fmt.Errorf("%w: dep=%q runbook path required (SR06 §12AI.2 governance)", ErrInvalidDependency, d.Name)
	}
	return nil
}

// ErrInvalidDependency is returned by Validate on malformed entries.
var ErrInvalidDependency = errors.New("dependencies: invalid dependency entry")

// ErrFallbackCycle is returned by LoadAndValidate on a fallback DAG cycle.
var ErrFallbackCycle = errors.New("dependencies: fallback cycle detected")

// ErrUnknownFallback is returned by LoadAndValidate when a fallback name
// is not present in the matrix.
var ErrUnknownFallback = errors.New("dependencies: unknown fallback dep")

// ErrDuplicateDependency is returned by LoadAndValidate when two
// dependencies share a name.
var ErrDuplicateDependency = errors.New("dependencies: duplicate dependency name")
