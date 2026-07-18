package api

// CD4 · the ship gate (Track D · WS-D3).
//
//	"A curated workflow MUST NOT reference a tool that has not passed G1–G4."
//
// The verdicts come from `contracts/tool-liveness.json`, GENERATED from the liveness
// matrix (`scripts/eval/tool_liveness/manifest.py`) and never hand-maintained. The copy
// embedded here is byte-identical to the SoT — `TestLivenessManifestMatchesContract`
// reds if they drift.
//
// The manifest carries two DERIVED fields so this gate and chat-service's `tool_list`
// filter do not re-implement the verdict logic in two languages (the schema-drift trap):
//
//	executes  true  the tool ran when called correctly
//	          false the tool FAILED when called correctly — proven broken
//	          null  never checked (paid, no authored args, or no probe)
//	proven    every gate G1..G4 passed under a real model
//
// The three-valued `executes` is the whole point. `null` must NEVER be read as `false`:
// "we didn't check" is not "it's broken", and blocking on unknown would reject a step
// referencing any of the ~200 tools that have no probe yet. Hence `blocked()` tests for
// an EXPLICIT false.
//
// Why a proven-broken tool is REJECTED here, while CD4's phasing says "warn in WS-D3":
// that phasing was written when the matrix had a single, undifferentiated RED, which
// conflated "the model didn't select it" (an F5 description problem — harmless for a
// workflow, whose runner calls the step's tool directly and needs no selection) with
// "the tool is broken" (an F6 product bug). Rejecting on an ambiguous RED would have
// blocked steps that reference perfectly good tools. Now that the harness scores those
// apart, rejecting on `executes == false` is unambiguous and safe TODAY.
//
// The WARNING fires on `executes == null` (UNCHECKED), NOT on `!proven`. CD4's verdict
// table is explicit: a tool proven to EXECUTE (executes == true) is admitted with NO
// warning even when it is not `proven` (every gate G1–G4 under a model) — because `proven`
// includes G1 ("did a model pick this tool from its description?"), and a workflow step
// NAMES its tool directly, so selection is irrelevant to it. Warning on `!proven` would
// flag every tool the deterministic sweep proved executes (126 of them) — noise that
// buries the ~73 tools with no execution evidence at all. (`proven` remains a separate,
// higher-confidence signal; it is simply not the warning trigger.)

import (
	_ "embed"
	"encoding/json"
	"log/slog"
	"sort"
)

//go:embed tool-liveness.json
var livenessManifestJSON []byte

type toolLiveness struct {
	Status   string `json:"status"`
	Executes *bool  `json:"executes"` // pointer: nil == "never checked"
	Proven   bool   `json:"proven"`
}

type livenessManifest struct {
	SchemaVersion int                     `json:"schema_version"`
	Source        string                  `json:"source"`
	Tools         map[string]toolLiveness `json:"tools"`
}

var liveness = loadLiveness()

func loadLiveness() livenessManifest {
	var m livenessManifest
	if err := json.Unmarshal(livenessManifestJSON, &m); err != nil {
		// Degrade-safe: an unreadable manifest must not brick workflow authoring. The
		// gate goes inert and says so, loudly, rather than rejecting every workflow.
		slog.Error("tool-liveness manifest unreadable — CD4 ship gate is INERT", "err", err)
		return livenessManifest{Tools: map[string]toolLiveness{}}
	}
	return m
}

// toolBlocked reports whether the tool is PROVEN BROKEN (executes == false). Only an
// explicit false blocks; an absent tool or a null `executes` is unknown, not broken.
func toolBlocked(tool string) bool {
	t, ok := liveness.Tools[tool]
	return ok && t.Executes != nil && !*t.Executes
}

// toolUnchecked reports whether the tool has NO execution evidence either way — never
// probed (absent from the manifest) or probed but inconclusive (executes == null). This is
// the CD4 warning trigger. A tool proven to EXECUTE (executes == true) is NOT unchecked
// even if it is not `proven` (G1–G4 under a model): a workflow step names its tool
// directly, so a selection failure (the only thing separating "executes" from "proven") is
// irrelevant to it. Only "we have never seen this run" warrants the caveat.
func toolUnchecked(tool string) bool {
	t, ok := liveness.Tools[tool]
	return !ok || t.Executes == nil
}

// livenessWarnings returns one `unproven_tool` warning per distinct UNCHECKED tool the
// workflow references (executes == null or absent), sorted so the response is
// deterministic. A proven-broken tool is not warned about — it is REJECTED outright by
// validateWorkflow — and a tool proven to execute needs no caveat at all.
func livenessWarnings(steps []workflowStepIn) []string {
	seen := map[string]bool{}
	for _, st := range steps {
		if st.Tool != "" && toolUnchecked(st.Tool) && !toolBlocked(st.Tool) {
			seen[st.Tool] = true
		}
	}
	if len(seen) == 0 {
		return nil
	}
	names := make([]string, 0, len(seen))
	for n := range seen {
		names = append(names, n)
	}
	sort.Strings(names)
	out := make([]string, 0, len(names))
	for _, n := range names {
		out = append(out, "unproven_tool: '"+n+"' has not been shown to execute "+
			"(no successful call is recorded in the liveness manifest). It may fail at run "+
			"time; see docs/eval/tool-liveness/.")
	}
	return out
}
