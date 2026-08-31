package provider

import (
	"encoding/json"
	"fmt"
	"sort"
)

// responsesBodyShape describes an outbound /v1/responses body WITHOUT its content, for logging
// when the provider rejects it.
//
// 🔴 WHY A SHAPE AND NOT THE BODY. D-UPSTREAM-ERROR-WITH-NO-MESSAGE has now defeated sixteen
// hypotheses, and every one of them was tested against a RECONSTRUCTION of the failing request
// rather than the request itself — turn length, payload size, load, encoding, context pressure,
// the supplier tool, pass count, turn count, service state, mid-turn widening, surface size, an
// invalid tool schema. Each reconstruction succeeded where the real call failed, which is the
// signature of measuring the wrong thing. What was missing was never a cleverer theory; it was
// the outbound request.
//
// The body itself is the author's manuscript text and cannot be logged. Its SHAPE can: how many
// tools, how many input items and of what kinds, whether the turn chains, and how big each part
// is. That is enough to tell a malformed request from a large one from a chained one, and it
// carries no prose.
//
// Emitted ONLY when the stream failed, so a healthy turn costs nothing.
type responsesBodyShape struct {
	Tools         int            `json:"tools"`
	ToolsBytes    int            `json:"tools_bytes"`
	InputItems    int            `json:"input_items"`
	InputKinds    map[string]int `json:"input_kinds"`
	InputBytes    int            `json:"input_bytes"`
	InstrBytes    int            `json:"instructions_bytes"`
	Chained       bool           `json:"chained"`
	Store         bool           `json:"store"`
	MaxOutput     any            `json:"max_output_tokens,omitempty"`
	Reasoning     string         `json:"reasoning_effort,omitempty"`
	TotalBytes    int            `json:"total_bytes"`
	ToolsNoParams []string       `json:"tools_without_properties,omitempty"`
	// Per-tool JSON Schema constructs beyond a plain object-with-properties, as
	// "toolName:construct". A provider that rejects a request without saying why gives no
	// index to bisect on, and 9 of the 65 tools in the failing turn are consumer-local and
	// absent from the federated catalogue, so no offline probe can even send them. This is
	// how an unusual schema anywhere in the surface becomes visible without logging schemas.
	ToolsUnusual []string `json:"tools_unusual_schema,omitempty"`
	// Every top-level key of the outbound body, sorted. A reconstruction can only send the
	// keys its author knows about, and a probe that sends 63 real tools, the real chain, the
	// real content and the real magnitudes still SUCCEEDS where this request fails — so what
	// separates them is something the reconstruction never included. This names it without
	// logging a byte of it.
	BodyKeys []string `json:"body_keys"`
}

// unusualSchemaConstructs walks a JSON Schema and names the constructs a strict validator is
// most likely to reject. It reports; it decides nothing. Bounded in depth so a pathological
// schema cannot make a diagnostic expensive.
func unusualSchemaConstructs(v any, depth int, found map[string]bool) {
	if depth > 8 {
		return
	}
	switch t := v.(type) {
	case map[string]any:
		for _, k := range []string{"$ref", "$defs", "definitions", "oneOf", "anyOf", "allOf",
			"not", "patternProperties", "additionalItems", "if", "then", "else",
			"prefixItems", "const", "dependentSchemas"} {
			if _, has := t[k]; has {
				found[k] = true
			}
		}
		// A `type` given as a LIST ("type": ["string","null"]) is valid JSON Schema and is
		// exactly the shape a provider's stricter validator tends to refuse.
		if _, isList := t["type"].([]any); isList {
			found["type-as-list"] = true
		}
		for _, sub := range t {
			unusualSchemaConstructs(sub, depth+1, found)
		}
	case []any:
		for _, sub := range t {
			unusualSchemaConstructs(sub, depth+1, found)
		}
	}
}

// describeResponsesBody summarises the body. Never returns an error and never panics on a shape
// it does not recognise — a diagnostic that can take the turn down is worse than no diagnostic.
func describeResponsesBody(body map[string]any) responsesBodyShape {
	s := responsesBodyShape{InputKinds: map[string]int{}}
	if b, err := json.Marshal(body); err == nil {
		s.TotalBytes = len(b)
	}
	if v, ok := body["previous_response_id"].(string); ok && v != "" {
		s.Chained = true
	}
	if v, ok := body["store"].(bool); ok {
		s.Store = v
	}
	s.MaxOutput = body["max_output_tokens"]
	if r, ok := body["reasoning"].(map[string]any); ok {
		if e, ok := r["effort"].(string); ok {
			s.Reasoning = e
		}
	}
	if v, ok := body["instructions"].(string); ok {
		s.InstrBytes = len(v)
	}
	if tools, ok := body["tools"].([]any); ok {
		s.Tools = len(tools)
		if b, err := json.Marshal(tools); err == nil {
			s.ToolsBytes = len(b)
		}
		for _, t := range tools {
			tm, ok := t.(map[string]any)
			if !ok {
				continue
			}
			// The one malformation already known to draw a flat rejection from LM Studio:
			// an object schema with no `properties`. Named here so a recurrence is legible
			// rather than needing to be re-derived.
			p, ok := tm["parameters"].(map[string]any)
			if !ok || p["type"] != "object" {
				continue
			}
			name, _ := tm["name"].(string)
			if _, has := p["properties"]; !has {
				s.ToolsNoParams = append(s.ToolsNoParams, name)
			}
			found := map[string]bool{}
			unusualSchemaConstructs(p, 0, found)
			for k := range found {
				s.ToolsUnusual = append(s.ToolsUnusual, name+":"+k)
			}
		}
	}
	if in, ok := body["input"].([]any); ok {
		s.InputItems = len(in)
		if b, err := json.Marshal(in); err == nil {
			s.InputBytes = len(b)
		}
		for _, it := range in {
			im, ok := it.(map[string]any)
			if !ok {
				s.InputKinds["<not-an-object>"]++
				continue
			}
			kind, _ := im["type"].(string)
			if kind == "" {
				if r, ok := im["role"].(string); ok {
					kind = "message:" + r
				} else {
					kind = "<no-type>"
				}
			} else if kind == "message" {
				if r, ok := im["role"].(string); ok {
					kind = "message:" + r
				}
			}
			s.InputKinds[kind]++
		}
	}
	for k := range body {
		s.BodyKeys = append(s.BodyKeys, k)
	}
	sort.Strings(s.BodyKeys)
	sort.Strings(s.ToolsNoParams)
	sort.Strings(s.ToolsUnusual)
	return s
}

// String renders the shape as compact JSON for a log field.
func (s responsesBodyShape) String() string {
	b, err := json.Marshal(s)
	if err != nil {
		return fmt.Sprintf("<unrenderable shape: %v>", err)
	}
	return string(b)
}
