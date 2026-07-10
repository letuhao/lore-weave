package api

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// The embedded manifest MUST be byte-identical to the generated SoT. It is a copy only
// because neither go:embed nor Python package data can climb out of its module; both are
// written by scripts/eval/tool_liveness/manifest.py. Hand-editing either is the drift
// this test exists to catch.
func TestLivenessManifestMatchesContract(t *testing.T) {
	// NOT a skip. A drift lock that quietly skips is worse than no drift lock — it reports
	// green while checking nothing. If the SoT moves, this must go red.
	sot, err := os.ReadFile(filepath.Join("..", "..", "..", "..", "contracts", "tool-liveness.json"))
	if err != nil {
		t.Fatalf("contracts/tool-liveness.json unreadable (%v) — the drift lock cannot run. "+
			"Fix the path; do not skip.", err)
	}
	if strings.ReplaceAll(string(sot), "\r\n", "\n") != strings.ReplaceAll(string(livenessManifestJSON), "\r\n", "\n") {
		t.Fatal("embedded tool-liveness.json has DRIFTED from contracts/tool-liveness.json — " +
			"re-run: python -m scripts.eval.tool_liveness.manifest <matrix.json>")
	}
}

func TestLivenessManifestParsesAndIsNonEmpty(t *testing.T) {
	if len(liveness.Tools) == 0 {
		t.Fatal("liveness manifest is empty — the CD4 gate would be silently inert")
	}
	if liveness.SchemaVersion != 1 {
		t.Errorf("schema_version = %d, want 1 (bump the reader when you bump the schema)", liveness.SchemaVersion)
	}
}

// ── the three-valued `executes`, which is the entire point ───────────────────────
//
// `null` means NOT CHECKED. Reading it as false would reject a step referencing any of
// the ~200 tools that have no probe yet; reading it as true would let a broken tool ship.

func withLiveness(t *testing.T, body string, fn func()) {
	t.Helper()
	saved := liveness
	defer func() { liveness = saved }()
	var m livenessManifest
	if err := json.Unmarshal([]byte(body), &m); err != nil {
		t.Fatalf("bad fixture: %v", err)
	}
	liveness = m
	fn()
}

const _fixture = `{"schema_version":1,"tools":{
  "good_tool":   {"status":"PASS","executes":true,"proven":true},
  "broken_tool": {"status":"RED-CAPABILITY","executes":false,"proven":false},
  "unchecked":   {"status":"RED","executes":null,"proven":false},
  "works_but_unpicked": {"status":"RED-SELECT","executes":true,"proven":false}
}}`

func TestToolBlockedOnlyOnExplicitFalse(t *testing.T) {
	withLiveness(t, _fixture, func() {
		if toolBlocked("good_tool") {
			t.Error("a proven tool must not be blocked")
		}
		if !toolBlocked("broken_tool") {
			t.Error("executes=false must block — it failed when called with valid args")
		}
		if toolBlocked("unchecked") {
			t.Error(`executes=null must NOT block — "we didn't check" is not "it's broken"`)
		}
		if toolBlocked("never_probed_at_all") {
			t.Error("an absent tool has no probe; it is unproven, not broken")
		}
		if toolBlocked("works_but_unpicked") {
			t.Error("RED-SELECT means the tool WORKS — a workflow step names its tool " +
				"directly, so selection is irrelevant here")
		}
	})
}

func TestUnprovenCoversAbsentAndNonPassing(t *testing.T) {
	withLiveness(t, _fixture, func() {
		if toolUnproven("good_tool") {
			t.Error("a PASS tool is proven")
		}
		for _, n := range []string{"broken_tool", "unchecked", "works_but_unpicked", "absent"} {
			if !toolUnproven(n) {
				t.Errorf("%q must be unproven", n)
			}
		}
	})
}

func TestLivenessWarningsAreDeterministicAndSkipBlocked(t *testing.T) {
	withLiveness(t, _fixture, func() {
		steps := []workflowStepIn{
			{ID: "s3", Tool: "unchecked"},
			{ID: "s1", Tool: "good_tool"},          // proven — no warning
			{ID: "s2", Tool: "works_but_unpicked"}, // unproven — warns
			{ID: "s4", Tool: "unchecked"},          // dupe — one warning only
			{ID: "s5", Tool: "broken_tool"},        // BLOCKED — rejected, never warned about
		}
		w := livenessWarnings(steps)
		if len(w) != 2 {
			t.Fatalf("want 2 warnings (deduped, blocked excluded), got %d: %v", len(w), w)
		}
		// sorted → unchecked before works_but_unpicked
		if !strings.Contains(w[0], "'unchecked'") || !strings.Contains(w[1], "'works_but_unpicked'") {
			t.Errorf("warnings must be sorted for a deterministic response: %v", w)
		}
		for _, s := range w {
			if !strings.Contains(s, "unproven_tool") {
				t.Errorf("warning must carry the unproven_tool code: %q", s)
			}
		}
	})
}

func TestValidateWorkflowRejectsAProvenBrokenTool(t *testing.T) {
	withLiveness(t, _fixture, func() {
		in := &workflowInput{
			Slug: "wf-broken", Description: "d", Surfaces: []string{"chat"},
			Steps: []workflowStepIn{{ID: "step-one", Tool: "broken_tool"}},
		}
		msg, ok := validateWorkflow(in)
		if ok {
			t.Fatal("a workflow step referencing a known-broken tool must be REJECTED")
		}
		if !strings.Contains(msg, "known-broken") || !strings.Contains(msg, "broken_tool") {
			t.Errorf("rejection must name the tool and why: %q", msg)
		}
	})
}

func TestValidateWorkflowAdmitsUncheckedAndSelectFailingTools(t *testing.T) {
	withLiveness(t, _fixture, func() {
		for _, tool := range []string{"unchecked", "works_but_unpicked", "never_probed_at_all"} {
			in := &workflowInput{
				Slug: "wf-ok", Description: "d", Surfaces: []string{"chat"},
				Steps: []workflowStepIn{{ID: "step-one", Tool: tool}},
			}
			if _, ok := validateWorkflow(in); !ok {
				t.Errorf("tool %q must be ADMITTED (warn, not block) — it is unproven, not broken", tool)
			}
		}
	})
}
