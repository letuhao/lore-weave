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
	const marker = "List the curated multi-step workflows"
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

// 🔴 THE PAYLOAD GUARD WAS REMOVED AFTER ITS OWN FIX MEASURED WORSE, 2026-08-26.
//
// The description under-declares its result: it says "slug + title + description" and the
// tool returns five fields (workflowMeta adds tier and status). That is still TRUE, and a
// guard asserting "describe what you return" stood here.
//
// Correcting the sentence to name all five made the ANSWERS WORSE, isolated by a control that
// changed nothing else:
//     c-regwf7  corrected description : 3/5 registry_list_workflows, 2/5 workflow_list
//                                       and those 2 listed ALL TWELVE workflows for a
//                                       question that named the STUDIO surface
//     c-regwf8  reverted, one line     : 5/5 registry_list_workflows, 0 wrong
//     c-regwf6  before any of it, K=20 : 20/20 registry_list_workflows, 0 wrong
//
// Mentioning `tier` and `status` on a tool answering a SURFACE question apparently makes it
// read as less apt for the ask. The mechanism is not established; the effect is.
//
// So the guard is gone rather than left red: keeping a test that demands a change measured to
// hurt would make the next person ship it. The DEFECT stays open in the ledger with this
// measurement on it. This is the SECOND time this exact tool pair has punished an accuracy
// fix — the twin's self-filter wording was reverted for the same reason.

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
