package config

import (
	"strings"
	"testing"

	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

func TestDefault_ValidatesClean(t *testing.T) {
	c := Default()
	if err := c.Validate(); err != nil {
		t.Fatalf("default config should validate clean; got %v", err)
	}
	if len(c.Tables) != len(types.L3ATables) {
		t.Errorf("default should configure all %d L3.A tables; got %d", len(types.L3ATables), len(c.Tables))
	}
	for _, tbl := range c.Tables {
		if tbl.SampleSize != 20 {
			t.Errorf("default SampleSize=20 expected, got %d for %s", tbl.SampleSize, tbl.TableName)
		}
	}
}

func TestValidate_RejectsUnknownMode(t *testing.T) {
	c := Default()
	c.Mode = "weekly"
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for unknown mode")
	}
}

func TestValidate_RejectsTableOutsideAllowlist(t *testing.T) {
	c := Default()
	c.Tables = append(c.Tables, types.TableConfig{
		TableName:         "rogue_projection",
		SampleSize:        20,
		FullScanBatchSize: 500,
	})
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for rogue table")
	}
}

func TestValidate_RejectsZeroSampleSizeInDaily(t *testing.T) {
	c := Default()
	c.Tables[0].SampleSize = 0
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for SampleSize=0 in daily mode")
	}
}

func TestValidate_RejectsZeroBatchInMonthly(t *testing.T) {
	c := Default()
	c.Mode = types.CheckModeMonthly
	c.Tables[0].FullScanBatchSize = 0
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for FullScanBatchSize=0 in monthly mode")
	}
}

func TestValidate_RejectsZeroIntervalInMonthly(t *testing.T) {
	c := Default()
	c.Mode = types.CheckModeMonthly
	c.FullCheckIntervalDays = 0
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for full_check_interval_days=0 in monthly mode")
	}
}

func TestParse_MinimalYAML(t *testing.T) {
	yaml := `
mode: monthly
daily_enabled: false
monthly_enabled: true
full_check_interval_days: 30
tables:
  - name: pc_projection
    sample_size: 50
    full_scan_batch_size: 1000
  - name: npc_projection
    sample_size: 25
    full_scan_batch_size: 750
`
	cfg, err := parse(yaml)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if cfg.Mode != types.CheckModeMonthly {
		t.Errorf("Mode=monthly expected, got %s", cfg.Mode)
	}
	if cfg.DailyEnabled {
		t.Error("DailyEnabled=false expected")
	}
	if !cfg.MonthlyEnabled {
		t.Error("MonthlyEnabled=true expected")
	}
	if cfg.FullCheckIntervalDays != 30 {
		t.Errorf("FullCheckIntervalDays=30 expected, got %d", cfg.FullCheckIntervalDays)
	}
	if len(cfg.Tables) != 2 {
		t.Fatalf("2 tables expected, got %d", len(cfg.Tables))
	}
	if cfg.Tables[0].TableName != "pc_projection" || cfg.Tables[0].SampleSize != 50 || cfg.Tables[0].FullScanBatchSize != 1000 {
		t.Errorf("table[0] mismatch: %+v", cfg.Tables[0])
	}
	if cfg.Tables[1].TableName != "npc_projection" || cfg.Tables[1].SampleSize != 25 {
		t.Errorf("table[1] mismatch: %+v", cfg.Tables[1])
	}
}

func TestParse_IgnoresUnknownKeys_ForwardCompat(t *testing.T) {
	yaml := `
mode: daily
future_knob: 42
tables:
  - name: pc_projection
    sample_size: 20
    full_scan_batch_size: 500
`
	cfg, err := parse(yaml)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if cfg.Mode != types.CheckModeDaily {
		t.Errorf("unknown key future_knob broke parse; mode=%s", cfg.Mode)
	}
}

func TestLoadFile_EmptyPathReturnsDefault(t *testing.T) {
	c, err := LoadFile("")
	if err != nil {
		t.Fatalf("LoadFile(\"\"): %v", err)
	}
	if c.Mode != types.CheckModeDaily {
		t.Errorf("default mode should be daily")
	}
}

func TestParse_HandlesInlineComment(t *testing.T) {
	yaml := `
mode: daily  # cycle-15 default
tables:
  - name: pc_projection  # canonical PC table
    sample_size: 20
    full_scan_batch_size: 500
`
	cfg, err := parse(yaml)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	if cfg.Mode != types.CheckModeDaily {
		t.Errorf("inline comment broke mode parse")
	}
	if !strings.HasPrefix(cfg.Tables[0].TableName, "pc_projection") {
		t.Errorf("inline comment broke table-name parse: got %q", cfg.Tables[0].TableName)
	}
}
