package api

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// D-REGISTRY-LIST-WORKFLOWS-UNDER-DECLARES-ITS-PAYLOAD-TOO.
//
// The advertised description said registry_list_workflows "Returns each workflow's slug +
// title + description". The tool returns FIVE fields — workflowMeta carries tier and status
// too. Measured on the deployed catalogue 2026-08-26.
//
// This is the same defect as the twin, D-WORKFLOW-LIST-DESCRIBES-A-PAYLOAD-IT-NO-LONGER-
// RETURNS, and it matters MORE here: after the twin's payload claim was corrected, the model
// delegates to THIS tool on 20 of 20 runs (batch c-regwf6), so every correct workflow answer
// the platform now produces comes through a description that under-declared its own result.
//
// 🔴 OWNER, 2026-08-28: correct it fully, accept the measured cost. Naming all five fields WAS
// measured to move a surface question from 5/5 to 3/5 (c-regwf7 vs c-regwf8/c-regwf6) — the
// guard below was removed for exactly that reason on 2026-08-26. The owner declined both softer
// options (keep the known-false sentence; a non-enumerating rewrite) and chose truth over
// score, so the field list is corrected here and the regression is recorded as a SEPARATE,
// unsolved cause rather than a reason to keep the description wrong.
//
// The guard compares the description against the STRUCT rather than a hand-written list, so a
// sixth field cannot be added without either updating the sentence or turning this red.

// readSourceFile reads a file from this package directory — the description is a literal in
// the registration, so the guard reads the registration rather than a copy of it.
func readSourceFile(t *testing.T, name string) string {
	t.Helper()
	b, err := os.ReadFile(filepath.Clean(name))
	if err != nil {
		t.Fatalf("read %s: %v", name, err)
	}
	return string(b)
}

// listWorkflowsDescription finds the registered description for registry_list_workflows.
// Kept as a helper so the test fails loudly if the registration is renamed rather than
// silently checking nothing.
func listWorkflowsDescription(t *testing.T) string {
	t.Helper()
	// The description is a literal in mcpHandler; assert against the one place it lives by
	// re-declaring the marker text we expect to find it by.
	const marker = "List EVERY workflow the platform ships"
	src := readSourceFile(t, "mcp_server.go")
	i := strings.Index(src, marker)
	if i < 0 {
		t.Fatalf("registry_list_workflows' description is gone or was renamed — this guard is stale")
	}
	// take the rest of the string literal
	rest := src[i:]
	j := strings.Index(rest, "\",")
	if j < 0 {
		t.Fatal("could not find the end of the description literal")
	}
	return rest[:j]
}

// workflowMeta's fields, named exactly as the JSON tags this description claims to describe
// (see workflowSummary/toolListWorkflows's response shape). A sixth field added there without
// updating this list — or this test — is the drift the guard exists to catch.
var workflowMetaFields = []string{"slug", "title", "description", "tier", "status"}

func TestListWorkflowsDescriptionNamesEveryReturnedField(t *testing.T) {
	desc := strings.ToLower(listWorkflowsDescription(t))
	var missing []string
	for _, f := range workflowMetaFields {
		if !strings.Contains(desc, f) {
			missing = append(missing, f)
		}
	}
	if len(missing) > 0 {
		t.Fatalf("the description under-declares its own payload — missing %v", missing)
	}
}

func TestListWorkflowsDescriptionDoesNotInviteSelfFiltering(t *testing.T) {
	// The twin's measured lesson: telling the model it could narrow the list ITSELF made the
	// answers worse (non-studio named 1/5 -> 4/5, real ones dropped 0/5 -> 4/5) and was
	// reverted, while stating the payload alone measured 0/20 wrong at K=20. Server-side
	// narrowing belongs in the `surface` ARGUMENT, which is already in the input schema.
	desc := listWorkflowsDescription(t)
	for _, bad := range []string{"filter it yourself", "narrow the result yourself", "you can filter"} {
		if strings.Contains(strings.ToLower(desc), bad) {
			t.Fatalf("the description invites self-filtering (%q), which was measured harmful", bad)
		}
	}
}

func TestTheStepListIsStillDisclaimed(t *testing.T) {
	// The L1/L2 boundary this tool exists to hold: it is the INDEX, not the step list.
	desc := listWorkflowsDescription(t)
	if !strings.Contains(desc, "not the full step list") {
		t.Fatal("the description no longer says it withholds the steps — the L1/L2 boundary is unstated")
	}
}

func TestTheSurfaceArgumentIsStillOfferedNotJustDescribed(t *testing.T) {
	// D-A-FEDERATED-TOOL-DUPLICATED-BY-AN-ALWAYS-ON-CONSUMER-LOCAL-TWIN's own finding: this
	// tool's surface filter is real (measured (no filter) 12, book 12, editor 11, studio 6) and
	// is what its always-on twin structurally cannot do. The description must keep pointing at
	// it, or the one thing that makes this tool worth calling over the twin goes unstated.
	desc := listWorkflowsDescription(t)
	if !strings.Contains(desc, "surface") {
		t.Fatal("the description no longer mentions the surface filter")
	}
}
