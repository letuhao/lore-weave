package loreweave_mcp

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"strconv"
)

// result_size.go — the HARD CAP on what an MCP tool may return.
//
// WHY THIS EXISTS. A tool's result lands verbatim in the calling agent's context window. A
// tool that returns more than the agent can hold is not merely wasteful — it is actively
// destructive, and it fails in a way that looks like a MODEL problem rather than a TOOL
// problem, which is why it survived so long:
//
//	Measured, 2026-07-12: `glossary_list_system_standards` returned **44,254 characters**
//	(~11k tokens — a THIRD of a chat turn's whole budget) because it inlined every kind's
//	full attribute definitions: 86% of the payload, and not one byte of it actionable (you
//	adopt a standard by CODE). In a live S06/S01 run, gemma called it TWENTY-FOUR times and
//	built nothing. Each call pushed the previous call's answer further out of the window, so
//	the model could never see what it had already fetched — so it fetched it again. Every
//	unit test was green. The tool "worked". The scenario was unwinnable.
//
// A tool whose result cannot fit in the context of the agent that calls it is not a tool.
// It is a context bomb with a friendly description. So the SDK now refuses to ship one.
//
// This is deliberately a HARD ERROR and it is deliberately ON BY DEFAULT. A soft warning
// would be filed under "known noise" within a week; an error gets the tool fixed. The tool
// author sees it the first time they call it, with the size and the ceiling in the message.
//
// Two thresholds, and the split between them is the whole design — learned from a review
// that caught the first cut breaking the platform:
//   - WARN (LW_MCP_RESULT_WARN_BYTES, default 8,000)   — LOGGED, every time, never fatal.
//     THIS is the "find broken tools" mechanism the human asked for. It is how the 44KB
//     glossary bomb was found. It fires on legitimate-but-chunky reads too, and that is
//     correct: a chunky read is worth a human's glance even when it is not a bug.
//   - MAX (LW_MCP_RESULT_MAX_BYTES, default 512,000)   — the tool call FAILS.
//
// The first cut set MAX to 32,000 and it was WRONG: a review measured that 88.7% of real
// books exceed 32KB on `glossary_book_ontology_read` ALONE, and a single ~5,300-word chapter
// blows it on `book_get_chapter` — both LEGITIMATE full-content reads. A blanket 32KB
// hard-fail with "do not retry" does not find broken tools; it bricks the flagship. Size
// cannot separate "a bloated payload of unused structure" (a bomb) from "a large blob of the
// exact content requested" (legitimate) — the 44KB bomb was SMALLER than a 117KB legitimate
// ontology. So the hard FAIL is a catastrophe backstop only (a query that forgot its LIMIT,
// a list that should have paginated), set well above any legitimate single read; the WARN,
// not the FAIL, is what surfaces bloat for a human to fix.
//
// Escape hatch: a service that legitimately must exceed even 512KB sets LW_MCP_RESULT_MAX_BYTES.
// No per-tool opt-out flag — an opt-out is how the 44KB payload would have dodged the WARN too.
const (
	defaultResultWarnBytes = 8_000
	defaultResultMaxBytes  = 512_000
)

func envInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			return n
		}
	}
	return def
}

// ResultWarnBytes / ResultMaxBytes are read once per call so a service can tune them via env
// without a rebuild (and so a test can flip them).
func ResultWarnBytes() int { return envInt("LW_MCP_RESULT_WARN_BYTES", defaultResultWarnBytes) }
func ResultMaxBytes() int  { return envInt("LW_MCP_RESULT_MAX_BYTES", defaultResultMaxBytes) }

// ErrResultTooLarge is returned to the CALLER (the agent) when a tool's structured result
// exceeds the hard cap. The message is written for two audiences at once: the agent, which
// must not retry it, and the human who has to go fix the tool.
type ErrResultTooLarge struct {
	Tool  string
	Bytes int
	Max   int
}

func (e *ErrResultTooLarge) Error() string {
	return fmt.Sprintf(
		"tool %q returned %d bytes, over the %d-byte MCP result ceiling. This is a BUG IN THE "+
			"TOOL, not in the caller: a result this large does not fit in the context of the "+
			"agent that called it, and it will crowd out the very question it was meant to "+
			"answer. Do not retry it. Fix the tool: return a summary or the identifiers the "+
			"caller can act on, paginate, or split the drill-down into a second tool.",
		e.Tool, e.Bytes, e.Max,
	)
}

// checkResultSize measures a tool's structured output and enforces the ceiling.
// Returns nil when the payload is acceptable (logging a warning if it is merely large).
func checkResultSize(toolName string, out any) error {
	b, err := json.Marshal(out)
	if err != nil {
		// Not our failure to diagnose — the SDK will surface the marshal error itself.
		return nil
	}
	n := len(b)
	max := ResultMaxBytes()
	if n > max {
		slog.Error("mcp tool result EXCEEDS the hard ceiling — the call was failed",
			"tool", toolName, "bytes", n, "max", max)
		return &ErrResultTooLarge{Tool: toolName, Bytes: n, Max: max}
	}
	if warn := ResultWarnBytes(); n > warn {
		slog.Warn("mcp tool result is large — it will crowd the caller's context window",
			"tool", toolName, "bytes", n, "warn_over", warn, "hard_max", max)
	}
	return nil
}
