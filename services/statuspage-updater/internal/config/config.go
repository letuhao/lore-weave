// Package config loads the L7.L config: components.yaml + banner-config.yaml.
//
// These are read once at startup. components.yaml maps incident-affected
// component ids onto status-page components; banner-config.yaml is the
// severity → banner policy projection (mirrors the cross-DPS severity matrix
// auto_banner column).
package config

import (
	"errors"
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

// Component is one row of components.yaml.
type Component struct {
	ID          string `yaml:"id"`
	Name        string `yaml:"name"`
	Description string `yaml:"description"`
	Group       string `yaml:"group"`
}

// Components is the top-level wrapper of components.yaml.
type Components struct {
	Version                int         `yaml:"version"`
	ShippedCycle           int         `yaml:"shipped_cycle"`
	ExpectedComponentCount int         `yaml:"expected_component_count"`
	Components             []Component `yaml:"components"`

	byID map[string]Component
}

// LoadComponents reads + validates components.yaml.
func LoadComponents(path string) (*Components, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("statuspage-updater: read components %s: %w", path, err)
	}
	var c Components
	if err := yaml.Unmarshal(raw, &c); err != nil {
		return nil, fmt.Errorf("statuspage-updater: parse components: %w", err)
	}
	if c.Version == 0 {
		return nil, errors.New("statuspage-updater: components.yaml missing version")
	}
	if c.ExpectedComponentCount > 0 && len(c.Components) != c.ExpectedComponentCount {
		return nil, fmt.Errorf("statuspage-updater: components drift — expected %d got %d", c.ExpectedComponentCount, len(c.Components))
	}
	c.byID = make(map[string]Component, len(c.Components))
	for i, comp := range c.Components {
		if comp.ID == "" {
			return nil, fmt.Errorf("statuspage-updater: component #%d missing id", i)
		}
		if _, dup := c.byID[comp.ID]; dup {
			return nil, fmt.Errorf("statuspage-updater: duplicate component id %q", comp.ID)
		}
		c.byID[comp.ID] = comp
	}
	return &c, nil
}

// Lookup returns a component by id.
func (c *Components) Lookup(id string) (Component, bool) {
	comp, ok := c.byID[id]
	return comp, ok
}

// IDs returns all component ids.
func (c *Components) IDs() []string {
	out := make([]string, 0, len(c.Components))
	for _, comp := range c.Components {
		out = append(out, comp.ID)
	}
	return out
}

// BannerRow is one row of banner-config.yaml banner_policy.
type BannerRow struct {
	Severity            string `yaml:"severity"`
	AutoBanner          bool   `yaml:"auto_banner"`
	StatuspageImpact    string `yaml:"statuspage_impact"`
	RequiresUserVisible bool   `yaml:"requires_user_visible"`
	DefaultTemplate     string `yaml:"default_template"`
}

// BannerConfig is the top-level wrapper of banner-config.yaml.
type BannerConfig struct {
	Version       int         `yaml:"version"`
	BannerPolicy  []BannerRow `yaml:"banner_policy"`
	ClearOnResolve bool       `yaml:"clear_on_resolve"`

	bySeverity map[string]BannerRow
}

// LoadBannerConfig reads + validates banner-config.yaml.
func LoadBannerConfig(path string) (*BannerConfig, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("statuspage-updater: read banner-config %s: %w", path, err)
	}
	var b BannerConfig
	if err := yaml.Unmarshal(raw, &b); err != nil {
		return nil, fmt.Errorf("statuspage-updater: parse banner-config: %w", err)
	}
	if b.Version == 0 {
		return nil, errors.New("statuspage-updater: banner-config.yaml missing version")
	}
	if len(b.BannerPolicy) != 4 {
		return nil, fmt.Errorf("statuspage-updater: banner_policy must cover all 4 severities; got %d", len(b.BannerPolicy))
	}
	b.bySeverity = make(map[string]BannerRow, len(b.BannerPolicy))
	for _, row := range b.BannerPolicy {
		if row.Severity == "" {
			return nil, errors.New("statuspage-updater: banner_policy row missing severity")
		}
		b.bySeverity[row.Severity] = row
	}
	for _, sev := range []string{"SEV0", "SEV1", "SEV2", "SEV3"} {
		if _, ok := b.bySeverity[sev]; !ok {
			return nil, fmt.Errorf("statuspage-updater: banner_policy missing %s", sev)
		}
	}
	return &b, nil
}

// PolicyFor returns the banner row for a severity.
func (b *BannerConfig) PolicyFor(severity string) (BannerRow, bool) {
	row, ok := b.bySeverity[severity]
	return row, ok
}
