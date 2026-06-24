// Package config loads sli_definitions.yaml + slo_targets.yaml from
// the contracts/slo/ registry. Loaded once at startup; the calculator
// computes burn rates against the in-memory tables.
//
// Q-L7-1 LOCKED: this service is SEPARATE from incident-bot +
// statuspage-updater. It exposes /healthz + /metrics + a small read
// API used by alertmanager rule evaluation; nothing else.
package config

import (
	"errors"
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

// SLI is one row of contracts/slo/sli_definitions.yaml.
type SLI struct {
	Name        string   `yaml:"name"`
	Description string   `yaml:"description"`
	Formula     string   `yaml:"formula"`
	Numerator   string   `yaml:"numerator"`
	Denominator string   `yaml:"denominator"`
	Window      string   `yaml:"window"`
	TierScope   []string `yaml:"tier_scope"`
	Labels      []string `yaml:"labels"`
	Owner       string   `yaml:"owner"`
	Runbook     string   `yaml:"runbook"`
}

// SLIDefinitions is the top-level wrapper of sli_definitions.yaml.
type SLIDefinitions struct {
	Version          int    `yaml:"version"`
	ShippedCycle     int    `yaml:"shipped_cycle"`
	SLIs             []SLI  `yaml:"slis"`
	ExpectedSLICount int    `yaml:"expected_sli_count"`
}

// SLOTarget is one row of contracts/slo/slo_targets.yaml.
type SLOTarget struct {
	SLIRef string  `yaml:"sli_ref"`
	Tier   string  `yaml:"tier"`
	Target float64 `yaml:"target"`
	Window string  `yaml:"window"`
}

// BurnRatePolicyTier is one row of the 4-tier burn response policy.
type BurnRatePolicyTier struct {
	Threshold float64 `yaml:"threshold"`
	Response  string  `yaml:"response"`
	PRLabel   string  `yaml:"pr_label"`
}

// SLOTargets is the top-level wrapper of slo_targets.yaml.
type SLOTargets struct {
	Version             int                  `yaml:"version"`
	ShippedCycle        int                  `yaml:"shipped_cycle"`
	Targets             []SLOTarget          `yaml:"targets"`
	BurnRateResponse    []BurnRatePolicyTier `yaml:"burn_rate_response"`
	ExpectedTargetCount int                  `yaml:"expected_target_count"`
}

// LoadSLIs loads + validates the SLI registry.
func LoadSLIs(path string) (*SLIDefinitions, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("slo-budget-calculator: read %s: %w", path, err)
	}
	var d SLIDefinitions
	if err := yaml.Unmarshal(raw, &d); err != nil {
		return nil, fmt.Errorf("slo-budget-calculator: parse %s: %w", path, err)
	}
	if d.Version == 0 {
		return nil, errors.New("slo-budget-calculator: sli_definitions.yaml missing version")
	}
	if d.ExpectedSLICount > 0 && len(d.SLIs) != d.ExpectedSLICount {
		return nil, fmt.Errorf(
			"slo-budget-calculator: drift — expected_sli_count=%d but got %d entries",
			d.ExpectedSLICount, len(d.SLIs),
		)
	}
	for i, s := range d.SLIs {
		if s.Name == "" {
			return nil, fmt.Errorf("slo-budget-calculator: sli #%d: name required", i)
		}
		if s.Numerator == "" || s.Denominator == "" {
			return nil, fmt.Errorf(
				"slo-budget-calculator: sli %s: numerator + denominator required (burn calc reads these)",
				s.Name,
			)
		}
		if s.Window == "" {
			return nil, fmt.Errorf("slo-budget-calculator: sli %s: window required", s.Name)
		}
	}
	return &d, nil
}

// LoadTargets loads + validates the SLO target registry.
func LoadTargets(path string) (*SLOTargets, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("slo-budget-calculator: read %s: %w", path, err)
	}
	var t SLOTargets
	if err := yaml.Unmarshal(raw, &t); err != nil {
		return nil, fmt.Errorf("slo-budget-calculator: parse %s: %w", path, err)
	}
	if t.Version == 0 {
		return nil, errors.New("slo-budget-calculator: slo_targets.yaml missing version")
	}
	if t.ExpectedTargetCount > 0 && len(t.Targets) != t.ExpectedTargetCount {
		return nil, fmt.Errorf(
			"slo-budget-calculator: drift — expected_target_count=%d but got %d entries",
			t.ExpectedTargetCount, len(t.Targets),
		)
	}
	if len(t.BurnRateResponse) != 4 {
		return nil, fmt.Errorf(
			"slo-budget-calculator: burn_rate_response must have exactly 4 tiers (SR1 §12AD.4); got %d",
			len(t.BurnRateResponse),
		)
	}
	for i, row := range t.Targets {
		if row.SLIRef == "" {
			return nil, fmt.Errorf("slo-budget-calculator: target #%d: sli_ref required", i)
		}
		if row.Target <= 0 || row.Target > 1 {
			return nil, fmt.Errorf(
				"slo-budget-calculator: target #%d (%s/%s): target must be in (0,1]; got %v",
				i, row.SLIRef, row.Tier, row.Target,
			)
		}
	}
	return &t, nil
}

// SLINames returns just the SLI name set (helper for tests + alert linting).
func (d *SLIDefinitions) SLINames() []string {
	names := make([]string, 0, len(d.SLIs))
	for _, s := range d.SLIs {
		names = append(names, s.Name)
	}
	return names
}

// TargetFor returns the SLO target row for a (sli, tier) tuple, or
// (nil, false) if not declared. Used by burn-rate calculator to decide
// whether a given (sli, tier) is in-scope.
func (t *SLOTargets) TargetFor(sliRef, tier string) (*SLOTarget, bool) {
	for i, row := range t.Targets {
		if row.SLIRef == sliRef && row.Tier == tier {
			return &t.Targets[i], true
		}
	}
	return nil, false
}
