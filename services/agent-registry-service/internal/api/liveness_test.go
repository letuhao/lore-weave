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
	if liveness.SchemaVersion != 2 {
		t.Errorf("schema_version = %d, want 2 (v2 adds waived:{reason,gate}; reader ignores it — CD4 still gates on executes:false)", liveness.SchemaVersion)
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

func TestUncheckedCoversAbsentAndNullOnly(t *testing.T) {
	withLiveness(t, _fixture, func() {
		// "unchecked" = no execution evidence: executes==null, or absent from the manifest.
		for _, n := range []string{"unchecked", "absent"} {
			if !toolUnchecked(n) {
				t.Errorf("%q must be unchecked (null executes / absent from manifest)", n)
			}
		}
		// A tool that EXECUTES is NOT unchecked — even when it is not `proven` (RED-SELECT).
		// This is the whole fix: warning on `!proven` flagged these; warning on unchecked
		// does not.
		for _, n := range []string{"good_tool", "works_but_unpicked"} {
			if toolUnchecked(n) {
				t.Errorf("%q executes (executes==true) — it must NOT be unchecked", n)
			}
		}
		// executes==false is evidence too — it is REJECTED, not merely "unchecked".
		if toolUnchecked("broken_tool") {
			t.Error("executes=false is execution evidence, not 'unchecked'")
		}
	})
}

func TestLivenessWarningsWarnOnlyOnUncheckedTools(t *testing.T) {
	withLiveness(t, _fixture, func() {
		steps := []workflowStepIn{
			{ID: "s1", Tool: "good_tool"},          // executes + proven — no warning
			{ID: "s2", Tool: "works_but_unpicked"}, // executes (RED-SELECT) — NO warning (CD4 §table)
			{ID: "s3", Tool: "unchecked"},          // executes==null — warns
			{ID: "s4", Tool: "unchecked"},          // dupe — one warning only
			{ID: "s5", Tool: "broken_tool"},        // BLOCKED — rejected, never warned about
			{ID: "s6", Tool: "never_probed"},       // absent — unchecked — warns
		}
		w := livenessWarnings(steps)
		if len(w) != 2 {
			t.Fatalf("want 2 warnings (unchecked + absent; executing & blocked excluded), got %d: %v", len(w), w)
		}
		// sorted → "never_probed" before "unchecked"
		if !strings.Contains(w[0], "'never_probed'") || !strings.Contains(w[1], "'unchecked'") {
			t.Errorf("warnings must be sorted for a deterministic response: %v", w)
		}
		for _, s := range w {
			if !strings.Contains(s, "unproven_tool") {
				t.Errorf("warning must carry the unproven_tool code: %q", s)
			}
			// the regression this fix prevents: a tool that EXECUTES must never be warned about
			if strings.Contains(s, "works_but_unpicked") || strings.Contains(s, "good_tool") {
				t.Errorf("a tool proven to execute must not warn (CD4: RED-SELECT → no warning): %q", s)
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
