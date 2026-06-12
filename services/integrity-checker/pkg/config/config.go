// Package config loads contracts/integrity/config.yaml. Hand-rolled tiny
// YAML parser (no third-party dep) — config has a fixed, simple shape and
// the archive-worker / retention-worker pattern is dependency-light.
package config

import (
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"

	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

// Config is the parsed integrity-checker configuration.
type Config struct {
	// Mode is "daily" or "monthly". Drives which orchestrator runs at
	// `cmd/integrity-checker/main.go` startup.
	Mode types.CheckMode
	// DailyEnabled gates the daily cron entirely. False = service exits 0
	// without running the loop. Used by the cycle-15 IaC to roll out the
	// service in dark mode first.
	DailyEnabled bool
	// MonthlyEnabled gates the monthly cron entirely.
	MonthlyEnabled bool
	// FullCheckIntervalDays — only consulted in monthly mode; informs the
	// state writer's `expected_next_sweep_at` field. Cycle-15 default: 30.
	FullCheckIntervalDays int
	// Tables enumerates per-table budgets. Default: all 10 L3.A tables
	// with SampleSize=20, FullScanBatchSize=500.
	Tables []types.TableConfig
}

// Default returns the cycle-15 default configuration. Used by tests and as
// the fallback when the YAML file is absent.
func Default() Config {
	tables := make([]types.TableConfig, 0, len(types.L3ATables))
	for _, t := range types.L3ATables {
		tables = append(tables, types.TableConfig{
			TableName:         t,
			SampleSize:        20,
			FullScanBatchSize: 500,
		})
	}
	return Config{
		Mode:                  types.CheckModeDaily,
		DailyEnabled:          true,
		MonthlyEnabled:        true,
		FullCheckIntervalDays: 30,
		Tables:                tables,
	}
}

// Validate enforces the invariants the rest of the service relies on.
//   - Mode must be one of {daily, monthly}
//   - Every TableConfig.TableName must be in L3ATables (allowlist fence
//     matching the cycle-13 CHECK constraint)
//   - SampleSize > 0 in daily mode; FullScanBatchSize > 0 in monthly mode
//   - FullCheckIntervalDays > 0 in monthly mode
func (c Config) Validate() error {
	if !c.Mode.IsValid() {
		return fmt.Errorf("integrity-checker config: invalid mode %q (want daily|monthly)", c.Mode)
	}
	allow := map[string]struct{}{}
	for _, t := range types.L3ATables {
		allow[t] = struct{}{}
	}
	if len(c.Tables) == 0 {
		return errors.New("integrity-checker config: no tables configured")
	}
	for i, tbl := range c.Tables {
		if _, ok := allow[tbl.TableName]; !ok {
			return fmt.Errorf("integrity-checker config: table[%d] %q not in L3.A allowlist", i, tbl.TableName)
		}
		if c.Mode == types.CheckModeDaily && tbl.SampleSize <= 0 {
			return fmt.Errorf("integrity-checker config: table[%d] %q SampleSize must be > 0 in daily mode", i, tbl.TableName)
		}
		if c.Mode == types.CheckModeMonthly && tbl.FullScanBatchSize <= 0 {
			return fmt.Errorf("integrity-checker config: table[%d] %q FullScanBatchSize must be > 0 in monthly mode", i, tbl.TableName)
		}
	}
	if c.Mode == types.CheckModeMonthly && c.FullCheckIntervalDays <= 0 {
		return errors.New("integrity-checker config: full_check_interval_days must be > 0 in monthly mode")
	}
	return nil
}

// LoadFile reads the YAML file at path. Returns Default() if the path is
// empty (test/dev convenience). Caller should call Validate() after.
//
// The parser is intentionally minimal — recognized top-level keys only.
// Anything unknown is logged and ignored (forward-compatible). This avoids
// dragging in yaml.v3 for what is essentially a key=value file.
func LoadFile(path string) (Config, error) {
	if path == "" {
		return Default(), nil
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return Config{}, fmt.Errorf("integrity-checker config: read %s: %w", path, err)
	}
	return parse(string(data))
}

// parse implements the minimal YAML reader. Exposed for tests.
func parse(text string) (Config, error) {
	cfg := Default()
	// Walk lines; recognize "key: value" at top level, and a nested
	// `tables:` list of `- name:`/`sample_size:`/`full_scan_batch_size:`.
	lines := strings.Split(text, "\n")
	inTables := false
	var tables []types.TableConfig
	var curr *types.TableConfig
	for _, raw := range lines {
		line := strings.TrimRight(raw, "\r")
		// Strip trailing inline comment but ONLY when '#' is preceded by
		// whitespace (so values like `key#val` aren't truncated).
		if hash := strings.Index(line, " #"); hash >= 0 {
			line = line[:hash]
		}
		if strings.HasPrefix(strings.TrimSpace(line), "#") || strings.TrimSpace(line) == "" {
			continue
		}
		trimmed := strings.TrimSpace(line)
		if !strings.HasPrefix(line, " ") && !strings.HasPrefix(line, "\t") {
			inTables = false
			curr = nil
			key, val, ok := splitKV(trimmed)
			if !ok {
				continue
			}
			switch key {
			case "mode":
				cfg.Mode = types.CheckMode(strings.Trim(val, `"`))
			case "daily_enabled":
				cfg.DailyEnabled = parseBool(val)
			case "monthly_enabled":
				cfg.MonthlyEnabled = parseBool(val)
			case "full_check_interval_days":
				if n, err := strconv.Atoi(val); err == nil {
					cfg.FullCheckIntervalDays = n
				}
			case "tables":
				inTables = true
				tables = []types.TableConfig{}
			}
			continue
		}
		if !inTables {
			continue
		}
		// Inside tables: each list item starts with "- name:" or has
		// continuation keys "sample_size:" / "full_scan_batch_size:".
		if strings.HasPrefix(trimmed, "- ") {
			if curr != nil {
				tables = append(tables, *curr)
			}
			curr = &types.TableConfig{SampleSize: 20, FullScanBatchSize: 500}
			rest := strings.TrimPrefix(trimmed, "- ")
			if key, val, ok := splitKV(rest); ok && key == "name" {
				curr.TableName = strings.Trim(val, `"`)
			}
			continue
		}
		if curr == nil {
			continue
		}
		if key, val, ok := splitKV(trimmed); ok {
			switch key {
			case "name":
				curr.TableName = strings.Trim(val, `"`)
			case "sample_size":
				if n, err := strconv.Atoi(val); err == nil {
					curr.SampleSize = n
				}
			case "full_scan_batch_size":
				if n, err := strconv.Atoi(val); err == nil {
					curr.FullScanBatchSize = n
				}
			}
		}
	}
	if curr != nil {
		tables = append(tables, *curr)
	}
	if len(tables) > 0 {
		cfg.Tables = tables
	}
	return cfg, nil
}

func splitKV(line string) (string, string, bool) {
	idx := strings.Index(line, ":")
	if idx < 0 {
		return "", "", false
	}
	key := strings.TrimSpace(line[:idx])
	val := strings.TrimSpace(line[idx+1:])
	if key == "" {
		return "", "", false
	}
	return key, val, true
}

func parseBool(s string) bool {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "true", "yes", "1":
		return true
	default:
		return false
	}
}
