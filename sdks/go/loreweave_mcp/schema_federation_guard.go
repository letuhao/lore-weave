package loreweave_mcp

import (
	"encoding/json"
	"fmt"
	"sort"
	"strconv"
)

// ── The federation-safety gate: no BOOLEAN subschema, anywhere ──
//
// JSON Schema 2020-12 lets `true`/`false` stand in for a whole schema, and the
// go-sdk reflector emits `true` for any `any`/`interface{}`-typed field. That is
// perfectly legal JSON Schema — and ai-gateway's federation validator REJECTS it.
// The blast radius is the PROVIDER, not the tool: one bad schema fails the whole
// `tools/list` response, so every sibling tool disappears from the catalog.
//
// This shipped for real (2026-07-23). `glossary_curation_list` typed its
// discriminated-union payload as `Items any`:
//
//	WARN [FederationService] provider 'glossary' list-tools failed → PARTIAL:
//	  path: ["tools", 12, "outputSchema", "properties", "items"]
//	LOG  [FederationService] catalog: 235 tools / 10 providers (... PARTIAL)
//
// ALL 54 glossary tools vanished from the federated catalog (measured: 0
// `glossary_*` of 245). Every same-language gate stayed green, because the schema
// is valid IN ISOLATION — the defect only exists at the federation boundary, in
// another service, in another language, in another validator.
//
// `RegisterTool` already handled the coarse case (`Out = any`, see register_tool.go)
// by substituting an explicit object schema. It did NOT catch a NESTED `any` FIELD
// inside an otherwise-typed struct — which is exactly how this shipped. So check the
// FINAL schemas instead of guessing from Go types: whatever the reflector produced,
// or whatever the caller hand-wrote, must contain no boolean subschema.
//
// This fails LOUDLY at registration (i.e. at service boot, deterministically) rather
// than degrading silently in production. A silent `PARTIAL` that erases a provider is
// precisely the "no silent seams" failure this repo keeps re-learning.
//
// Fix for a flagged tool: set an explicit `OutputSchema`/`InputSchema` on the
// `mcp.Tool` stating the real shape, e.g. for a union payload
//
//	&jsonschema.Schema{Type: "object", Properties: map[string]*jsonschema.Schema{
//	    "items": {Type: "array", Items: &jsonschema.Schema{Type: "object"}},
//	}}
//
// See `curationListOutputSchema()` in glossary-service for the worked example.

// nonSubschemaKeywords are JSON Schema keywords whose value is NOT a schema, so a
// boolean sitting there is legitimate and must not be flagged. Two groups:
//
//   - schema-OR-boolean keywords — `additionalProperties` above all: the go-sdk
//     infers `false` for every struct and the federation validator accepts it.
//   - INSTANCE-valued keywords (`default`, `const`, `enum`, `examples`) — these hold
//     example VALUES, so `default: true` on a plain bool field is completely normal.
//     Measured across the live catalog: all 12 apparent "hits" on the Python providers
//     were `.../properties/<flag>/default` — every one a false positive. Without this
//     group the gate would panic a service at boot over a boolean flag's default,
//     which is a far worse failure than the bug it prevents.
var nonSubschemaKeywords = map[string]bool{
	"additionalProperties":  true,
	"unevaluatedProperties": true,
	"unevaluatedItems":      true,
	"uniqueItems":           true,
	"readOnly":              true,
	"writeOnly":             true,
	"deprecated":            true,
	"exclusiveMinimum":      true, // draft-4 style boolean form, tolerated by some producers
	"exclusiveMaximum":      true,
	"default":               true,
	"const":                 true,
	"enum":                  true,
	"examples":              true,
}

// findBooleanSubschemas walks a marshalled schema and returns the JSON-pointer-ish
// paths of every boolean that sits where a SCHEMA belongs. Returns paths sorted for
// a deterministic error message.
func findBooleanSubschemas(root any, prefix string) []string {
	var found []string
	var walk func(node any, path string)
	walk = func(node any, path string) {
		switch n := node.(type) {
		case bool:
			found = append(found, path)
		case map[string]any:
			for k, v := range n {
				if nonSubschemaKeywords[k] {
					continue
				}
				walk(v, path+"/"+k)
			}
		case []any:
			for i, v := range n {
				walk(v, path+"/"+strconv.Itoa(i))
			}
		}
	}
	walk(root, prefix)
	sort.Strings(found)
	return found
}

// checkNoBooleanSubschemas returns an error naming every offending path in the
// tool's advertised schemas. Schemas are round-tripped through JSON so the check
// runs on exactly the bytes federation will see — not on the Go value, which can
// marshal differently.
func checkNoBooleanSubschemas(toolName string, inputSchema, outputSchema any) error {
	var bad []string
	for _, s := range []struct {
		label  string
		schema any
	}{{"inputSchema", inputSchema}, {"outputSchema", outputSchema}} {
		if s.schema == nil {
			continue
		}
		raw, err := json.Marshal(s.schema)
		if err != nil {
			// Unmarshalable schema is a different (louder) failure; the SDK's own
			// AddTool will surface it. Don't mask it with a confusing report here.
			continue
		}
		var decoded any
		if err := json.Unmarshal(raw, &decoded); err != nil {
			continue
		}
		bad = append(bad, findBooleanSubschemas(decoded, toolName+"."+s.label)...)
	}
	if len(bad) == 0 {
		return nil
	}
	return fmt.Errorf(
		"MCP tool %q has %d boolean subschema(s) — ai-gateway's federation validator rejects these "+
			"and drops EVERY tool of this provider from the catalog (measured: one such field erased "+
			"all 54 glossary tools). An `any`/`interface{}`-typed field reflects to `true`; declare an "+
			"explicit InputSchema/OutputSchema stating the real shape instead. Offending paths: %v",
		toolName, len(bad), bad)
}
