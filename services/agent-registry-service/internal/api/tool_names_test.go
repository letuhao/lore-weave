package api

import (
	"encoding/json"
	"os"
	"strings"
	"testing"
)

// A workflow step must not name a tool that does not exist.
//
// OWNER RULING 2026-08-31, DQ-T37: "validate that a proposed workflow step's tool name refers to
// a tool that exists. It is a cheap check at the one place the name enters the system, and the
// alternative is a workflow that fails at run time on a step nobody can fix without reading the
// registry."
//
// THE MEASUREMENT: of 10 proposed steps across 5 live cards, 3 named `chapter_compose`, which is
// not among the federated tools. A direct probe confirmed it at the boundary — a step with
// tool='totally_not_a_real_tool' was accepted and proposed. The tool already declared closed
// sets for surfaces[] and steps[].gate; steps[].tool was a free string.

func steps(tools ...string) []workflowStepIn {
	out := make([]workflowStepIn, 0, len(tools))
	for i, t := range tools {
		out = append(out, workflowStepIn{ID: "s" + string(rune('1'+i)), Tool: t})
	}
	return out
}

func TestUnknownToolIsRejected(t *testing.T) {
	if !toolUnknown("totally_not_a_real_tool") {
		t.Fatal("a fabricated name is not reported unknown — the gate is inert or the " +
			"contract is empty")
	}
	if !toolUnknown("chapter_compose") {
		t.Fatal("`chapter_compose`, the name that opened DQ-T37 and appeared in 3 of 10 " +
			"proposed steps, is not reported unknown")
	}
}

// 🔴 THE CONTROL THAT DECIDED THE DESIGN. The obvious implementation is "reject anything absent
// from the liveness manifest" — and it is wrong. That manifest carries 223 tools while the live
// catalogue carries 316, so 94 REAL tools are absent from it. Rejecting on that would block
// steps naming any of them. These are real tools that the liveness sweep has never probed.
func TestRealToolsAbsentFromTheLivenessManifestAreStillAccepted(t *testing.T) {
	var unprobed []string
	for name := range knownToolNames {
		if _, inManifest := liveness.Tools[name]; !inManifest {
			unprobed = append(unprobed, name)
		}
	}
	if len(unprobed) == 0 {
		t.Skip("every known tool is in the liveness manifest — the union no longer differs")
	}
	for _, name := range unprobed {
		if toolUnknown(name) {
			t.Fatalf("%q is a real tool absent from the liveness manifest and the gate calls "+
				"it unknown — the existence check has been narrowed to liveness", name)
		}
	}
}

func TestKnownToolsAreAccepted(t *testing.T) {
	for _, name := range []string{"book_list", "composition_generate", "glossary_search"} {
		if toolUnknown(name) {
			t.Fatalf("%q is a live tool and the gate calls it unknown", name)
		}
	}
}

// The gate must run at the chokepoint, not merely exist. A helper that returns the right answer
// is worth nothing if validateWorkflow never asks it.
func TestValidateWorkflowRejectsTheUnknownStep(t *testing.T) {
	in := &workflowInput{
		Slug: "wf-x", Title: "X", Description: "d",
		Steps: steps("book_list", "chapter_compose"),
	}
	msg, ok := validateWorkflow(in)
	if ok {
		t.Fatal("a workflow naming a non-existent tool was ACCEPTED — the recipe would be " +
			"saved under a name the author will trust and fail at run time")
	}
	if !strings.Contains(msg, "does not exist") {
		t.Fatalf("rejected for the wrong reason: %q", msg)
	}
	if !strings.Contains(msg, "tool_list") {
		t.Fatalf("the refusal does not say how to find the real names: %q", msg)
	}
}

func TestValidateWorkflowAcceptsAllRealSteps(t *testing.T) {
	in := &workflowInput{
		Slug: "wf-x", Title: "X", Description: "d",
		Steps: steps("book_list", "glossary_search"),
	}
	if msg, ok := validateWorkflow(in); !ok {
		t.Fatalf("a workflow of real tools was rejected: %q", msg)
	}
}

// 🔴 DEGRADE-SAFE, the same rule loadLiveness follows: an unreadable contract must make the gate
// INERT, never make it reject everything. A snapshot that fails to parse would otherwise brick
// workflow authoring platform-wide.
func TestAnEmptyContractMakesTheGateInertNotHostile(t *testing.T) {
	saved := knownToolNames
	knownToolNames = map[string]bool{}
	defer func() { knownToolNames = saved }()

	if toolUnknown("anything_at_all") {
		t.Fatal("with no contract loaded the gate rejects every tool — an unreadable " +
			"snapshot must not brick authoring")
	}
}

// The drift lock, mirroring TestLivenessManifestMatchesContract: the embedded copy and the
// contract are one artefact in two places, and a silent divergence means the service validates
// against a snapshot nobody can see.
func TestToolNamesMatchContract(t *testing.T) {
	onDisk, err := os.ReadFile("../../../../contracts/tool-names.json")
	if err != nil {
		t.Fatalf("contracts/tool-names.json unreadable (%v) — the drift lock cannot run", err)
	}
	var a, b toolNamesContract
	if err := json.Unmarshal(onDisk, &a); err != nil {
		t.Fatalf("contracts/tool-names.json is not valid JSON: %v", err)
	}
	if err := json.Unmarshal(toolNamesJSON, &b); err != nil {
		t.Fatalf("embedded tool-names.json is not valid JSON: %v", err)
	}
	if a.Count != b.Count || len(a.Tools) != len(b.Tools) {
		t.Fatalf("embedded tool-names.json has DRIFTED from contracts/tool-names.json "+
			"(%d vs %d tools) — regenerate with scripts/toolloop/tool_names.py",
			len(b.Tools), len(a.Tools))
	}
	for i := range a.Tools {
		if a.Tools[i] != b.Tools[i] {
			t.Fatalf("embedded tool-names.json has DRIFTED at index %d (%q vs %q) — "+
				"regenerate with scripts/toolloop/tool_names.py", i, b.Tools[i], a.Tools[i])
		}
	}
}
