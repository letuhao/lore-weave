package capacity

import (
	"errors"
	"fmt"
	"regexp"
	"strings"
)

// Class is the autoscaling-strategy classifier per R04 §12D.6 + SR08.
type Class string

const (
	ClassWeb        Class = "web"
	ClassLLMGateway Class = "llm-gateway"
	ClassWorker     Class = "worker"
	ClassCron       Class = "cron"
	ClassLibrary    Class = "library"
)

// Tier is one (v1|v3) capacity-plan slice. Fields are pointers so we
// can distinguish "field absent" (nil) from "field explicitly zero"
// (e.g., MinReplicas=0 is meaningful for cron / opt-in workers).
type Tier struct {
	MinReplicas      int    `yaml:"min_replicas"`
	MaxReplicas      int    `yaml:"max_replicas"`
	CPUPerReplica    *float64 `yaml:"cpu_per_replica,omitempty"`
	MemoryPerReplica string `yaml:"memory_per_replica,omitempty"`
	ScaleTrigger     string `yaml:"scale_trigger,omitempty"`
}

// Service is one entry under `services:` in budgets.yaml.
type Service struct {
	Name  string `yaml:"name"`
	Class Class  `yaml:"class"`
	V1    Tier   `yaml:"v1"`
	V3    Tier   `yaml:"v3"`
}

// Budgets is the loaded top-level structure.
type Budgets struct {
	Version  int       `yaml:"version"`
	Services []Service `yaml:"services"`
}

// Errors.
var (
	ErrInvalidService      = errors.New("capacity: invalid service entry")
	ErrUnsupportedVersion  = errors.New("capacity: unsupported budgets version")
	ErrDuplicateService    = errors.New("capacity: duplicate service name")
	ErrUnregisteredService = errors.New("capacity: service not in budgets.yaml")
	ErrUnknownYAMLKey      = errors.New("capacity: unknown YAML key (strict mode)")
)

// serviceNameRE — kebab-case + lowercase + digits. Matches every name
// in the shipped budgets.yaml (cycle 7). Allows single-char names
// (e.g. "a") for test fixtures; cycle-7 capacity-budget-lint.sh
// remains the directory-name source of truth in CI.
var serviceNameRE = regexp.MustCompile(`^[a-z]([a-z0-9-]*[a-z0-9])?$`)

// memorySuffixRE — Kubernetes resource-quantity suffix subset that the
// budgets.yaml uses. Accepts e.g., 512Mi, 2Gi, 1Ti, 256M, 1G.
var memorySuffixRE = regexp.MustCompile(`^[1-9][0-9]*(Mi|Gi|Ti|M|G|T|K|Ki)?$`)

// Validate inspects one Service for required fields + sane values.
func (s Service) Validate() error {
	if strings.TrimSpace(s.Name) == "" {
		return fmt.Errorf("%w: name empty", ErrInvalidService)
	}
	if !serviceNameRE.MatchString(s.Name) {
		return fmt.Errorf("%w: name=%q must be lowercase kebab-case", ErrInvalidService, s.Name)
	}
	switch s.Class {
	case ClassWeb, ClassLLMGateway, ClassWorker, ClassCron, ClassLibrary:
	default:
		return fmt.Errorf("%w: name=%q class=%q unknown", ErrInvalidService, s.Name, s.Class)
	}
	// library has no tiers — skip tier validation.
	if s.Class == ClassLibrary {
		return nil
	}
	if err := s.V1.validate("v1", s.Name); err != nil {
		return err
	}
	if err := s.V3.validateSparse("v3", s.Name); err != nil {
		return err
	}
	return nil
}

func (t Tier) validate(tierName, svcName string) error {
	if t.MinReplicas < 0 {
		return fmt.Errorf("%w: name=%q %s.min_replicas=%d must be >= 0", ErrInvalidService, svcName, tierName, t.MinReplicas)
	}
	if t.MaxReplicas <= 0 {
		return fmt.Errorf("%w: name=%q %s.max_replicas=%d must be > 0", ErrInvalidService, svcName, tierName, t.MaxReplicas)
	}
	if t.MaxReplicas < t.MinReplicas {
		return fmt.Errorf("%w: name=%q %s.max_replicas=%d < min_replicas=%d", ErrInvalidService, svcName, tierName, t.MaxReplicas, t.MinReplicas)
	}
	if t.CPUPerReplica == nil || *t.CPUPerReplica <= 0 {
		return fmt.Errorf("%w: name=%q %s.cpu_per_replica must be > 0", ErrInvalidService, svcName, tierName)
	}
	if !memorySuffixRE.MatchString(t.MemoryPerReplica) {
		return fmt.Errorf("%w: name=%q %s.memory_per_replica=%q invalid (e.g., 512Mi, 2Gi)", ErrInvalidService, svcName, tierName, t.MemoryPerReplica)
	}
	if strings.TrimSpace(t.ScaleTrigger) == "" {
		return fmt.Errorf("%w: name=%q %s.scale_trigger empty ('none' is required for cron)", ErrInvalidService, svcName, tierName)
	}
	return nil
}

// validateSparse is the v3 tier validator. v3 may inherit cpu/memory/
// scale_trigger from v1 — only min/max are required.
func (t Tier) validateSparse(tierName, svcName string) error {
	if t.MinReplicas < 0 {
		return fmt.Errorf("%w: name=%q %s.min_replicas=%d must be >= 0", ErrInvalidService, svcName, tierName, t.MinReplicas)
	}
	if t.MaxReplicas <= 0 {
		return fmt.Errorf("%w: name=%q %s.max_replicas=%d must be > 0", ErrInvalidService, svcName, tierName, t.MaxReplicas)
	}
	if t.MaxReplicas < t.MinReplicas {
		return fmt.Errorf("%w: name=%q %s.max_replicas=%d < min_replicas=%d", ErrInvalidService, svcName, tierName, t.MaxReplicas, t.MinReplicas)
	}
	return nil
}
