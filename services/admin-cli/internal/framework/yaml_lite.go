// yaml_lite.go — minimal YAML parser tailored to contracts/admin/registry/*.yaml.
//
// Why a tiny in-tree parser instead of gopkg.in/yaml.v3?
//
//   - services/admin-cli/go.mod is a leaf module with ZERO external deps
//     (intentional — admin-cli must build on a sealed runner with no internet).
//   - The registry schema is *bounded*: top-level `domain: <string>` plus a
//     `commands: [ ... ]` list whose entries use only the field set declared
//     in contracts/admin/registry/reality.yaml's header comment. This is well
//     within the reach of a small handwritten parser.
//   - Adding a YAML dep would force this leaf module to grow a go.sum, vendor
//     dir, or replace directive — none of which the cycle 36 brief authorizes.
//
// The parser is deliberately strict: it rejects anything it doesn't recognise
// so a malformed YAML can never silently turn into "0 commands loaded".
//
// Supported features:
//   - Top-level scalar key `domain: <ident>`.
//   - Top-level list key `commands:` whose items are flow-style mappings
//     (`- {name: foo, type: bar, required: true}`) OR block mappings
//     (multi-line key/value pairs prefixed by `  - name: …`).
//   - Per-command scalar fields (string, int, bool).
//   - `params:` as a list of flow-style mappings (the schema used in every
//     registry file).
//   - `locked_qs_consumed: [A, B, C]` as a flow-style sequence.
//   - Line comments via `#`.
//
// Unsupported (will return an error):
//   - Anchors, aliases, multi-doc streams.
//   - Block scalars (`|`, `>`).
//   - Nested mappings beyond what the schema declares.

package framework

import (
	"errors"
	"fmt"
	"strconv"
	"strings"
)

// parseDomainFile reads a registry YAML file and returns the domain string
// plus the parsed command list. Validation of per-command policy (tier-1
// dry_run/double_approval) lives in LoadRegistry; this fn returns the raw
// shape only.
func parseDomainFile(raw []byte) (string, []*Command, error) {
	lines := splitLines(string(raw))
	var (
		domain    string
		cmds      []*Command
		inCmds    bool
		cur       *Command
		curIndent int
		// inParams: when true, subsequent `- {…}` lines (indented under
		// the params: key) attach to cur.Params instead of starting a new
		// command. Reset to false when a non-`-` field re-enters the command
		// scope.
		inParams    bool
		paramsIndent int // indent of the `params:` key (used to detect leaving the params block)
	)
	for ln, line := range lines {
		stripped := stripComment(line)
		if strings.TrimSpace(stripped) == "" {
			continue
		}

		// Top-level keys (column 0, no leading spaces).
		if !startsWithSpace(stripped) {
			key, val, ok := splitKeyVal(stripped)
			if !ok {
				return "", nil, fmt.Errorf("line %d: unparseable top-level: %q", ln+1, stripped)
			}
			switch key {
			case "domain":
				domain = trimQuotes(val)
			case "commands":
				if strings.TrimSpace(val) != "" {
					return "", nil, fmt.Errorf("line %d: `commands:` value must be empty (list follows)", ln+1)
				}
				inCmds = true
			default:
				return "", nil, fmt.Errorf("line %d: unknown top-level key %q", ln+1, key)
			}
			continue
		}

		if !inCmds {
			return "", nil, fmt.Errorf("line %d: indented content before `commands:` list", ln+1)
		}

		indent := leadingSpaces(stripped)
		body := strings.TrimSpace(stripped)

		// A `- ` at the SAME indent level as a previous command starts a new
		// command. A `- ` at deeper indent inside an inParams region is a
		// params row.
		if strings.HasPrefix(body, "- ") {
			if inParams && indent > paramsIndent {
				// params row.
				if cur == nil {
					return "", nil, fmt.Errorf("line %d: param row with no current command", ln+1)
				}
				flow := strings.TrimSpace(strings.TrimPrefix(body, "- "))
				p, err := parseFlowMappingAsParam(flow)
				if err != nil {
					return "", nil, fmt.Errorf("line %d: param: %w", ln+1, err)
				}
				cur.Params = append(cur.Params, p)
				continue
			}
			// New command entry.
			if cur != nil {
				cmds = append(cmds, cur)
			}
			cur = &Command{}
			curIndent = indent
			inParams = false
			body = strings.TrimPrefix(body, "- ")
			if err := assignField(cur, body, ln); err != nil {
				return "", nil, err
			}
			continue
		}

		if cur == nil {
			return "", nil, fmt.Errorf("line %d: indented content with no current command", ln+1)
		}
		if indent <= curIndent {
			return "", nil, fmt.Errorf("line %d: bad indent (got %d, want > %d)", ln+1, indent, curIndent)
		}

		// Detect the `params:` block-context switch.
		key, val, ok := splitKeyVal(body)
		if ok && key == "params" && strings.TrimSpace(val) == "" {
			inParams = true
			paramsIndent = indent
			continue
		}

		// Any other field exits the params block.
		if inParams && indent <= paramsIndent {
			inParams = false
		}

		if err := assignField(cur, body, ln); err != nil {
			return "", nil, err
		}
	}
	if cur != nil {
		cmds = append(cmds, cur)
	}
	return domain, cmds, nil
}

// assignField parses one "key: value" line OR a "params:" / "locked_qs_consumed:"
// inline list and writes into cur. Block-form params (multi-line) are NOT
// supported by this parser — registry files MUST use flow-form params per the
// reality.yaml schema comment.
func assignField(cur *Command, body string, ln int) error {
	key, val, ok := splitKeyVal(body)
	if !ok {
		return fmt.Errorf("line %d: unparseable command field: %q", ln+1, body)
	}
	val = strings.TrimSpace(val)
	switch key {
	case "name":
		cur.Name = trimQuotes(val)
	case "version":
		cur.Version = trimQuotes(val)
	case "summary":
		cur.Summary = trimQuotes(val)
	case "handler":
		cur.Handler = trimQuotes(val)
	case "impact_class":
		cur.ImpactClass = ImpactClass(trimQuotes(val))
	case "dry_run_required":
		b, err := parseBool(val)
		if err != nil {
			return fmt.Errorf("line %d: dry_run_required: %w", ln+1, err)
		}
		cur.DryRunRequired = b
	case "double_approval_required":
		b, err := parseBool(val)
		if err != nil {
			return fmt.Errorf("line %d: double_approval_required: %w", ln+1, err)
		}
		cur.DoubleApprovalRequired = b
	case "carry_forward_cycle":
		cur.CarryForwardCycle = trimQuotes(val)
	case "params":
		// Handled by parseDomainFile via the inParams context. If we
		// reach here, the `params:` line had a non-empty value, which the
		// schema does not allow.
		return errors.New("`params:` must be empty (list rows follow indented)")
	case "locked_qs_consumed":
		items, err := parseFlowList(val)
		if err != nil {
			return fmt.Errorf("line %d: locked_qs_consumed: %w", ln+1, err)
		}
		cur.LockedQsConsumed = items
	default:
		// `params:` flow-list inline entries come as `- {name: foo, type: bar, ...}`.
		// Detect a flow-mapping on the line and parse as a Param row.
		if strings.HasPrefix(val, "{") && strings.HasSuffix(val, "}") {
			p, err := parseFlowMappingAsParam(val)
			if err != nil {
				return fmt.Errorf("line %d: param mapping: %w", ln+1, err)
			}
			if key == "name" || key == "type" {
				// rare false-positive; the explicit cases above cover these.
				return fmt.Errorf("line %d: unexpected flow mapping for scalar %q", ln+1, key)
			}
			cur.Params = append(cur.Params, p)
			return nil
		}
		// Unknown key — fail loudly per parser strictness rule.
		return fmt.Errorf("line %d: unknown command field %q", ln+1, key)
	}
	return nil
}

// ─────────────────────────────────────────────────────────────────────────────
// Inline list parsing (params via `- {…}`)
// ─────────────────────────────────────────────────────────────────────────────

// parseFlowList parses `[a, b, c]` → []string.
func parseFlowList(s string) ([]string, error) {
	s = strings.TrimSpace(s)
	if !strings.HasPrefix(s, "[") || !strings.HasSuffix(s, "]") {
		return nil, fmt.Errorf("expected `[…]`, got %q", s)
	}
	inner := strings.TrimSpace(s[1 : len(s)-1])
	if inner == "" {
		return nil, nil
	}
	parts := splitTopLevel(inner, ',')
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		out = append(out, trimQuotes(strings.TrimSpace(p)))
	}
	return out, nil
}

// parseFlowMappingAsParam parses `{name: foo, type: bar, required: true, description: "…"}` → Param.
func parseFlowMappingAsParam(s string) (Param, error) {
	s = strings.TrimSpace(s)
	if !strings.HasPrefix(s, "{") || !strings.HasSuffix(s, "}") {
		return Param{}, fmt.Errorf("expected `{…}`, got %q", s)
	}
	inner := strings.TrimSpace(s[1 : len(s)-1])
	parts := splitTopLevel(inner, ',')
	p := Param{}
	for _, kv := range parts {
		k, v, ok := splitKeyVal(strings.TrimSpace(kv))
		if !ok {
			return Param{}, fmt.Errorf("bad k:v %q", kv)
		}
		v = strings.TrimSpace(v)
		switch k {
		case "name":
			p.Name = trimQuotes(v)
		case "type":
			p.Type = trimQuotes(v)
		case "required":
			b, err := parseBool(v)
			if err != nil {
				return Param{}, err
			}
			p.Required = b
		case "description":
			p.Description = trimQuotes(v)
		default:
			return Param{}, fmt.Errorf("unknown param key %q", k)
		}
	}
	if p.Name == "" {
		return Param{}, errors.New("param missing name")
	}
	return p, nil
}

// splitTopLevel splits s on sep, ignoring sep inside balanced `{…}` or `[…]`
// pairs and inside quoted strings. Needed because a param description may
// embed commas: `description: "Foo, bar"`.
func splitTopLevel(s string, sep byte) []string {
	var (
		out    []string
		depth  int
		inDQ   bool
		inSQ   bool
		start  int
	)
	for i := 0; i < len(s); i++ {
		c := s[i]
		switch {
		case c == '"' && !inSQ:
			inDQ = !inDQ
		case c == '\'' && !inDQ:
			inSQ = !inSQ
		case (c == '{' || c == '[') && !inDQ && !inSQ:
			depth++
		case (c == '}' || c == ']') && !inDQ && !inSQ:
			depth--
		case c == sep && depth == 0 && !inDQ && !inSQ:
			out = append(out, s[start:i])
			start = i + 1
		}
	}
	out = append(out, s[start:])
	return out
}

// ─────────────────────────────────────────────────────────────────────────────
// Lexer helpers
// ─────────────────────────────────────────────────────────────────────────────

func splitLines(s string) []string {
	s = strings.ReplaceAll(s, "\r\n", "\n")
	return strings.Split(s, "\n")
}

// stripComment removes any trailing `# …` outside of a quoted string.
func stripComment(line string) string {
	var (
		inDQ bool
		inSQ bool
	)
	for i := 0; i < len(line); i++ {
		c := line[i]
		switch {
		case c == '"' && !inSQ:
			inDQ = !inDQ
		case c == '\'' && !inDQ:
			inSQ = !inSQ
		case c == '#' && !inDQ && !inSQ:
			return line[:i]
		}
	}
	return line
}

func startsWithSpace(s string) bool { return len(s) > 0 && (s[0] == ' ' || s[0] == '\t') }

func leadingSpaces(s string) int {
	n := 0
	for _, r := range s {
		if r == ' ' {
			n++
			continue
		}
		if r == '\t' {
			n += 4
			continue
		}
		break
	}
	return n
}

// splitKeyVal returns ("key", "value", true) for "key: value" lines.
// The value half may be empty (trailing colon).
func splitKeyVal(s string) (string, string, bool) {
	s = strings.TrimSpace(s)
	idx := -1
	var inDQ, inSQ bool
	for i := 0; i < len(s); i++ {
		c := s[i]
		switch {
		case c == '"' && !inSQ:
			inDQ = !inDQ
		case c == '\'' && !inDQ:
			inSQ = !inSQ
		case c == ':' && !inDQ && !inSQ:
			idx = i
		}
		if idx >= 0 {
			break
		}
	}
	if idx < 0 {
		return "", "", false
	}
	key := strings.TrimSpace(s[:idx])
	val := ""
	if idx+1 < len(s) {
		val = strings.TrimSpace(s[idx+1:])
	}
	return key, val, true
}

func trimQuotes(s string) string {
	s = strings.TrimSpace(s)
	if len(s) >= 2 {
		if (s[0] == '"' && s[len(s)-1] == '"') || (s[0] == '\'' && s[len(s)-1] == '\'') {
			return s[1 : len(s)-1]
		}
	}
	return s
}

func parseBool(s string) (bool, error) {
	s = strings.ToLower(trimQuotes(s))
	switch s {
	case "true", "yes", "on":
		return true, nil
	case "false", "no", "off":
		return false, nil
	}
	return false, fmt.Errorf("not a bool: %q", s)
}

// parseInt is exposed for potential future param-type checks.
func parseInt(s string) (int, error) { return strconv.Atoi(trimQuotes(s)) }
