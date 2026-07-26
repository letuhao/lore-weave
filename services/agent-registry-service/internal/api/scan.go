package api

import (
	"regexp"
	"strings"
	"time"
)

// ── REG-P3-05 supply-chain scan (OWASP Agentic Skills Top-10 derived) ────────
//
// An external MCP server's tool descriptions + input schemas are attacker-controlled
// text that lands in the model's context. A poisoned description ("ignore previous
// instructions and exfiltrate…") is the canonical tool-poisoning / cross-tool-
// shadowing attack. On register + rescan we fetch tools/list and lint every
// description/schema; a HIGH finding QUARANTINES the server (status=suspended) so it
// is never advertised until a human accept-risks it or the server is cleaned + rescanned.

type injectionMarker struct {
	re       *regexp.Regexp
	label    string
	severity string // "high" | "medium"
}

// (?i) case-insensitive; \s+ tolerates spacing tricks. Ordered high→medium.
var injectionMarkers = []injectionMarker{
	{regexp.MustCompile(`(?i)ignore\s+(all\s+)?(the\s+)?previous\s+(instructions|prompts?|messages?)`), "prompt-override:ignore-previous", "high"},
	{regexp.MustCompile(`(?i)disregard\s+(all\s+)?(the\s+)?(previous|prior|above)`), "prompt-override:disregard", "high"},
	{regexp.MustCompile(`(?i)(reveal|print|repeat|show|leak|exfiltrate)\s+(your|the)\s+(system\s+prompt|instructions|api\s*key|secret|token|credentials?)`), "exfiltration:reveal-secrets", "high"},
	{regexp.MustCompile(`(?i)do\s+not\s+(tell|inform|mention\s+to|reveal\s+to)\s+the\s+user`), "stealth:hide-from-user", "high"},
	{regexp.MustCompile(`(?i)you\s+are\s+now\s+(a|an|the)\b`), "persona-hijack:you-are-now", "high"},
	{regexp.MustCompile(`(?i)<\s*(system|important|secret)\s*>`), "hidden-instruction:pseudo-tag", "high"},
	{regexp.MustCompile(`(?i)\bBEGIN\s+SYSTEM\b|\bEND\s+SYSTEM\b`), "hidden-instruction:system-fence", "high"},
	{regexp.MustCompile(`(?i)(send|post|upload|forward)\s+(this|the|all|it)\b.{0,40}\b(to|https?://)`), "exfiltration:send-data", "medium"},
	{regexp.MustCompile(`(?i)before\s+(using|calling|running)\s+any\s+other\s+tool`), "shadowing:pre-empt-other-tools", "medium"},
	{regexp.MustCompile(`(?i)override\s+(the\s+)?(user|assistant|previous)`), "prompt-override:override", "medium"},
}

// Zero-width / bidi-control characters used to hide instructions from human review:
// ZWSP/ZWNJ/ZWJ/word-joiner/BOM (U+200B-200D, 2060, FEFF) + bidi overrides
// (U+202A-202E, 2066-2069). Expressed as escapes so no BOM lands in source.
var hiddenUnicode = regexp.MustCompile(`[\x{200B}-\x{200D}\x{2060}\x{FEFF}\x{202A}-\x{202E}\x{2066}-\x{2069}]`)

type scanFinding struct {
	Tool     string `json:"tool"`
	Field    string `json:"field"` // "description" | "schema" | "name"
	Marker   string `json:"marker"`
	Severity string `json:"severity"`
	Snippet  string `json:"snippet"`
}

type scannedTool struct {
	Name        string `json:"name"`
	Description string `json:"description"`
	Flagged     bool   `json:"flagged"` // has ≥1 high-severity finding
}

type scanResult struct {
	ScannedAt time.Time     `json:"scanned_at"`
	Clean     bool          `json:"clean"`
	ToolCount int           `json:"tool_count"`
	Findings  []scanFinding `json:"findings"`
	Tools     []scannedTool `json:"tools"` // per-tool summary for the detail tool browser
}

// probedTool is the subset of an MCP tools/list entry the scanner needs.
type probedTool struct {
	Name        string `json:"name"`
	Description string `json:"description"`
	InputSchema string `json:"input_schema"` // raw JSON text of the schema
}

// scanField lints one text blob for a given tool/field, appending findings.
func scanField(tool, field, text string, out *[]scanFinding) {
	if hiddenUnicode.MatchString(text) {
		*out = append(*out, scanFinding{Tool: tool, Field: field, Marker: "obfuscation:hidden-unicode", Severity: "high", Snippet: snippet(text)})
	}
	for _, m := range injectionMarkers {
		if loc := m.re.FindStringIndex(text); loc != nil {
			*out = append(*out, scanFinding{Tool: tool, Field: field, Marker: m.label, Severity: m.severity, Snippet: snippet(text[loc[0]:])})
		}
	}
}

// scanTools produces the verdict. clean = no HIGH-severity finding (mediums are
// advisory — surfaced but do not by themselves quarantine).
func scanTools(tools []probedTool) scanResult {
	res := scanResult{ScannedAt: time.Now().UTC(), ToolCount: len(tools), Findings: []scanFinding{}, Tools: []scannedTool{}}
	for _, t := range tools {
		before := len(res.Findings)
		scanField(t.Name, "name", t.Name, &res.Findings)
		scanField(t.Name, "description", t.Description, &res.Findings)
		scanField(t.Name, "schema", t.InputSchema, &res.Findings)
		flagged := false
		for _, f := range res.Findings[before:] {
			if f.Severity == "high" {
				flagged = true
				break
			}
		}
		res.Tools = append(res.Tools, scannedTool{Name: t.Name, Description: snippet(t.Description), Flagged: flagged})
	}
	res.Clean = true
	for _, f := range res.Findings {
		if f.Severity == "high" {
			res.Clean = false
			break
		}
	}
	return res
}

func snippet(s string) string {
	s = strings.TrimSpace(s)
	const max = 120
	if len(s) > max {
		return s[:max] + "…"
	}
	return s
}
