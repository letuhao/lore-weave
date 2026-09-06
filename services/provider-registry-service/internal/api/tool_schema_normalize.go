package api

// A function tool's `parameters` must be a COMPLETE object schema. A tool that takes no
// arguments declares `"properties": {}` — it does not omit the key.
//
// 🔴 MEASURED 2026-09-01, and it is the cause D-UPSTREAM-ERROR-WITH-NO-MESSAGE spent fourteen
// refuted hypotheses looking for. Probed directly against LM Studio's streaming /v1/responses,
// one tool per request:
//
//	{"additionalProperties":false,"type":"object"}                  -> HTTP 400 Invalid input
//	{"additionalProperties":false,"type":"object","properties":{}}  -> ACCEPTED
//	{"type":"object","properties":{}}                               -> ACCEPTED
//	{"type":"object"}                                               -> HTTP 400 Invalid input
//
// THE REJECTION IS NOT SCOPED TO THE OFFENDING TOOL. The provider refuses the WHOLE request and
// names the index — `"param":"tools.30"` — so ONE no-argument tool anywhere in the surface kills
// the entire turn, every other tool with it. That is why the failure looked scenario-specific
// and defeated hypotheses about turn length, payload size, load, encoding, context pressure,
// pass count, turn count, service state and mid-turn widening: none of them was ever about
// schema VALIDITY, and the four affected tools ride the domain hot set onto some surfaces and
// not others.
//
// Four of the 316 catalogue tools shipped the shape — glossary_list_system_standards,
// settings_get_defaults, settings_get_profile, settings_list_providers — i.e. exactly the tools
// that take no arguments.
//
// NORMALISED HERE, at the single door every provider's tools pass through, rather than in the
// four tools: the schemas are valid JSON Schema and their services are entitled to emit them, a
// per-provider adapter fix would have to be written three times (openai, anthropic, responses)
// and remembered for the fourth, and the next no-argument tool anyone adds gets this for free.
//
// Conservative: it only ADDS an empty `properties` to an object schema that has none. It never
// edits a declared property, never touches a non-object schema, and leaves anything it does not
// recognise exactly as it found it.
func normalizeToolParameters(tools any) any {
	arr, ok := tools.([]any)
	if !ok {
		return tools
	}
	for _, t := range arr {
		tm, ok := t.(map[string]any)
		if !ok {
			continue
		}
		// Both shapes reach here: OpenAI-nested ({function:{parameters}}) and the flat one.
		if fn, ok := tm["function"].(map[string]any); ok {
			fillEmptyProperties(fn)
		}
		fillEmptyProperties(tm)
	}
	return tools
}

// fillEmptyProperties gives `m["parameters"]` an empty `properties` object when it is an object
// schema declaring none. Mutates in place; a no-op for every other shape.
func fillEmptyProperties(m map[string]any) {
	params, ok := m["parameters"].(map[string]any)
	if !ok {
		return
	}
	if params["type"] != "object" {
		return
	}
	if _, has := params["properties"]; has {
		return
	}
	params["properties"] = map[string]any{}
}
