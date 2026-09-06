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

// ── EXISTENCE, which is a different question from liveness ────────────────────────────────
//
// 🔴 DQ-T37 (owner 2026-08-31): "validate that a proposed workflow step's tool name refers to a
// tool that exists". Measured on 5 live cards: of 10 proposed steps, 3 named `chapter_compose`,
// which is not among the federated tools. A direct probe confirmed it at the boundary — a step
// with tool='totally_not_a_real_tool' was accepted and proposed. Three of five proposals would
// have created a recipe that cannot run, saved under a name the author will trust later.
//
// 🔴 THE LIVENESS MANIFEST CANNOT ANSWER THIS, and reaching for it is the obvious wrong move.
// It carries 223 tools; the live catalogue carries 316; 94 REAL tools are in the catalogue and
// absent from the manifest. Rejecting on "absent from liveness" would block steps naming any of
// those 94. Hence a separate contract that is a UNION of both sources: absence from BOTH is the
// signal, and that is exactly what a hallucinated name looks like.
//
// The registry deliberately does NOT call ai-gateway for this — see probe.go on the
// agent-registry→ai-gateway dependency cycle. A generated contract file both sides read is the
// pattern this file already uses, drift-locked by a test.

//go:embed tool-names.json
var toolNamesJSON []byte

type toolNamesContract struct {
	Count int      `json:"count"`
	Tools []string `json:"tools"`
}

var knownToolNames = loadToolNames()

func loadToolNames() map[string]bool {
	var c toolNamesContract
	if err := json.Unmarshal(toolNamesJSON, &c); err != nil || len(c.Tools) == 0 {
		// Degrade-safe, the same way loadLiveness is: an unreadable contract must not brick
		// workflow authoring by rejecting every step. The gate goes INERT and says so.
		slog.Error("tool-names contract unreadable — the unknown-tool gate is INERT", "err", err)
		return map[string]bool{}
	}
	out := make(map[string]bool, len(c.Tools))
	for _, n := range c.Tools {
		out[n] = true
	}
	return out
}

// toolUnknown reports whether the platform has never heard of this tool name.
//
// 🔴 THE UNION IS TAKEN HERE, AT CHECK TIME, not only when the contract is generated. A name
// present in the LIVENESS manifest is known even if the names snapshot has not caught up: the
// two files are refreshed by different jobs, and a tool that has been probed but not yet
// re-snapshotted is real. Computing it here also means a test (or an operator) that swaps the
// liveness manifest gets a consistent answer instead of one baked in at build time — which is
// how this check first broke TestValidateWorkflowRejectsAProvenBrokenTool: its fixture tools
// are absent from the real snapshot, so an unknown-first gate rejected them for the wrong
// reason and hid the known-broken refusal behind a "does not exist".
//
// Returns false when the contract is empty (inert) — an unreadable snapshot must not reject
// real work.
func toolUnknown(tool string) bool {
	if len(knownToolNames) == 0 {
		return false
	}
	if knownToolNames[tool] {
		return false
	}
	_, inLiveness := liveness.Tools[tool]
	return !inLiveness
}
