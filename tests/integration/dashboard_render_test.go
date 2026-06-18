//go:build integration

package integration

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestDashboardRender_AllDashboardsConform — L7.H.12 (cycle 33).
//
// Walks dashboards/ tree, parses every *.json as Grafana dashboard JSON,
// and asserts conformance to dashboards/_library/STANDARDS.md.
//
// This is the contract-test counterpart to scripts/dashboard-validator.sh
// (the shell version runs in CI lint stage; this Go version runs in
// integration test stage). Both share the same allowed-UID set.
func TestDashboardRender_AllDashboardsConform(t *testing.T) {
	allowedUIDs := map[string]bool{
		"prom-primary":   true,
		"prom-secondary": true,
		"loki-primary":   true,
		"thanos-query":   true,
	}

	// Grandfathered cycle-6 dashboards exempted from cycle-33 STANDARDS.md.
	// RAID cycle 34 BACKFILLED the 6 pre-existing dashboards
	// (D-DASHBOARD-STANDARDS-BACKFILL row 062 ADDRESSED). Only TEMPLATE.json
	// remains exempted because its `_template` uid is intentional and would
	// fail the kebab-case rule.
	grandfathered := map[string]bool{
		"TEMPLATE.json": true, // intentionally non-kebab uid
	}

	root := "../../dashboards"
	var dashboards []string
	err := filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.IsDir() {
			return nil
		}
		if !strings.HasSuffix(path, ".json") || strings.HasSuffix(path, ".fixture.json") {
			return nil
		}
		if grandfathered[filepath.Base(path)] {
			return nil
		}
		dashboards = append(dashboards, path)
		return nil
	})
	if err != nil {
		t.Fatalf("walk dashboards: %v", err)
	}

	if len(dashboards) < 3 {
		// Cycle 33 adds 4 dashboards (1 logs-explorer + 2 platform + 1 TEMPLATE);
		// TEMPLATE is grandfathered. Floor is 3 (the cycle-33-strict subset).
		t.Fatalf("expected at least 3 non-grandfathered dashboards under %s; got %d", root, len(dashboards))
	}

	for _, p := range dashboards {
		t.Run(filepath.Base(p), func(t *testing.T) {
			raw, err := os.ReadFile(p)
			if err != nil {
				t.Fatalf("read %s: %v", p, err)
			}
			var d map[string]any
			if err := json.Unmarshal(raw, &d); err != nil {
				t.Fatalf("parse %s: %v", p, err)
			}

			// title non-empty
			if title, _ := d["title"].(string); title == "" {
				t.Errorf("%s: title missing/empty", p)
			}
			// uid non-empty
			uid, _ := d["uid"].(string)
			if uid == "" {
				t.Errorf("%s: uid missing/empty", p)
			}
			// panels list present
			panels, _ := d["panels"].([]any)
			if panels == nil {
				// Some dashboards may have empty panels at template stage; require
				// at least the key exists
				if _, ok := d["panels"]; !ok {
					t.Errorf("%s: panels key missing", p)
				}
			}
			// Every panel datasource.uid in LOCKED set
			for i, panel := range panels {
				pm, ok := panel.(map[string]any)
				if !ok {
					continue
				}
				if title, _ := pm["title"].(string); title == "" {
					t.Errorf("%s: panel #%d title missing", p, i+1)
				}
				if ds, ok := pm["datasource"].(map[string]any); ok {
					if dsUID, _ := ds["uid"].(string); dsUID != "" {
						if !allowedUIDs[dsUID] {
							t.Errorf("%s: panel #%d datasource.uid %q not in LOCKED set", p, i+1, dsUID)
						}
					}
				}
				// targets[].datasource.uid checks
				if targets, ok := pm["targets"].([]any); ok {
					for j, tgt := range targets {
						tm, ok := tgt.(map[string]any)
						if !ok {
							continue
						}
						if ds, ok := tm["datasource"].(map[string]any); ok {
							if dsUID, _ := ds["uid"].(string); dsUID != "" {
								if !allowedUIDs[dsUID] {
									t.Errorf("%s: panel #%d target #%d datasource.uid %q not in LOCKED set", p, i+1, j+1, dsUID)
								}
							}
						}
					}
				}
			}

			// refresh present
			if d["refresh"] == nil {
				t.Errorf("%s: refresh missing", p)
			}
			// time.from / time.to
			if tm, _ := d["time"].(map[string]any); tm == nil {
				t.Errorf("%s: time missing", p)
			} else {
				if tm["from"] == nil || tm["to"] == nil {
					t.Errorf("%s: time.from/to missing", p)
				}
			}
			// timezone
			if d["timezone"] == nil {
				t.Errorf("%s: timezone missing", p)
			}
		})
	}
}

// TestDashboardRender_NewCycle33Dashboards — assert the 4 new dashboards
// shipped this cycle exist (catches accidental delete).
func TestDashboardRender_NewCycle33Dashboards(t *testing.T) {
	expected := []string{
		"../../dashboards/_library/TEMPLATE.json",
		"../../dashboards/logs-explorer.json",
		"../../dashboards/platform/slo-summary.json",
		"../../dashboards/platform/meta-ha.json",
	}
	for _, f := range expected {
		if _, err := os.Stat(f); err != nil {
			t.Errorf("cycle-33 dashboard missing: %s (%v)", f, err)
		}
	}
}

// TestDashboardRender_StandardsDocPresent — STANDARDS.md exists at the
// LOCKED path. Verifier + lint both reference it.
func TestDashboardRender_StandardsDocPresent(t *testing.T) {
	if _, err := os.Stat("../../dashboards/_library/STANDARDS.md"); err != nil {
		t.Fatalf("STANDARDS.md missing: %v", err)
	}
}
