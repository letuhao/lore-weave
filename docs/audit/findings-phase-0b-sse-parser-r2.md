# Adversary Findings -- phase-0b-sse-parser -- Round 2

Design under review: docs/specs/2026-05-15-tilemap-phase-0b-gateway-tooluse.md (REVISED)
Phase: review-design / Agent: adversary / Round: 2
Status: REJECTED (1 BLOCK, 2 WARN)

Round-1 revision check: BLOCK-1 (empty-args first fragment) -- emit-rule prose added to D1, but see Finding 1 below: the fix is incomplete at the Go serialization layer. BLOCK-2 (tool_choice contract hole) -- D8 added; addressed in principle, but see Finding 2: the guard's closed allowlist creates a new hole. WARN-3 (Python discriminator parity + cross-SDK index) -- D5 now spells out the event_type / alias="event" idiom and the cross-SDK index default; this round-1 finding is adequately resolved at the prose level.

---

## Finding 1 -- BLOCK -- D3: arguments_delta with json:"...,omitempty" re-introduces the BLOCK-1 bug at the wire-serialization layer

D1's revised "Emit rule" correctly fixes the parse-side guard: streamOpenAICompat will now emit a StreamChunkToolCall for the first fragment even when its arguments is empty, because id/name are present. But D3 then specifies the Go struct field as ArgumentsDelta string json:"arguments_delta,omitempty". Go's omitempty drops an empty string from the marshalled JSON entirely. So the emitted chunk for the first fragment -- the one that carries the only id+name for that index -- serializes to {"event":"tool_call","id":"call_abc","name":"submit_zone_classifications"} with NO arguments_delta key at all. The streamer's emit guard was fixed; the wire encoding then silently undoes it. Two downstream consequences: (a) if the openapi ToolCallEvent lists arguments_delta in required (as event/delta siblings are -- see TokenEvent required:[event,delta]), the gateway emits a frame that fails its own schema; (b) D1 explicitly states "arguments_delta is therefore an allowed-empty string in the schema" -- omitempty contradicts that, because an allowed-empty-string field that is elided when empty is indistinguishable on the wire from an absent field. The existing StreamChunk.Delta is also omitempty, but token deltas are guarded never-empty; tool-call fragments are explicitly allowed-empty, so the same tag is wrong here.

Question for the designer: Where does the revised design state whether ToolCallEvent.arguments_delta is required or optional in the openapi, and -- if it is meant to always be present per-frame -- why is the Go field tagged json:"arguments_delta,omitempty" instead of a non-omitempty json:"arguments_delta", given that the entire BLOCK-1 fix depends on the first fragment surviving serialization with an empty arguments_delta? As written, D1's parse-side emit rule and D3's serialize-side omitempty are mutually contradictory and the id/name-bearing frame reaches the SDK accumulator with the field missing.

---

## Finding 2 -- BLOCK -- D8: providerSupportsTools is a closed allowlist with no default-permit and no documented behavior for unknown provider kinds

D8's guard helper providerSupportsTools(kind string) bool "returns true for openai-compat kinds (openai, lm_studio, ollama) and false for anthropic." This is a hard-coded closed allowlist. The provider-registry resolves providerKind from a DB column (um.provider_kind / platform_models.provider_kind) -- any kind value that is not one of those four (a newly-registered openai-compat-shaped provider, azure_openai, together, groq, deepseek, a renamed kind, a typo in seed data) falls through to false. The result: a genuinely tool-capable openai-compat provider returns 400 LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER even though ResolveAdapter would happily route it through streamOpenAICompat. The guard's intent is "fail loud when tools would be silently dropped," but a closed allowlist fails loud in the wrong direction for the open set of future openai-compat kinds -- and the spec gives no rule for the unknown case. This is the inverse of the round-1 contract hole: round 1 was "accept then silently drop"; D8 risks "reject something that would have worked," and silently couples a second hand-maintained string list to the adapter registry that ResolveAdapter already owns.

Question for the designer: When providerKind resolves to a value not in D8's four-kind allowlist, is the defined behavior to 400 (current reading -- breaks any future openai-compat provider) or to permit (then the Anthropic-silent-drop hole reopens for any future non-openai-compat kind)? Should providerSupportsTools instead be derived from the same source of truth ResolveAdapter uses to pick the streamer -- i.e. "does this adapter dispatch through streamOpenAICompat?" -- rather than a second, independently-maintained list that will drift from the adapter registry?

---

## Finding 3 -- WARN -- D4: Rust StreamEvent::ToolCall { index: u32 } is asymmetric with sibling Token/Reasoning { index: Option<u32> } in the same union; wire_format.rs must lock contradictory behavior for one JSON key

D4 and D5 mandate the new Rust variant carry index as a plain u32 with #[serde(default)] (NOT Option), so the accumulator always has a concrete key. But models.rs lines 175-184 show the existing StreamEvent::Token and StreamEvent::Reasoning variants declare index: Option<u32> with #[serde(default, skip_serializing_if = "Option::is_none")]. After this change the single StreamEvent enum has two representations of the same wire field index: nullable-Option for token/reasoning, defaulted-non-Option for tool_call. The Go side reuses ONE shared StreamChunk.Index int json:"index,omitempty" for all three kinds -- so the gateway emits index identically (elided when 0) regardless of kind, but the Rust decoder treats the same elided-or-present key under two different type contracts depending on the variant tag. AC-3 requires wire_format.rs to "lock the new event"; that test now has to assert serialize round-trips that are not consistent across the union -- a ToolCall with index 0 serializes the key (#[serde(default)] alone does NOT skip on serialize), while a Token with index None omits it. A frame {"event":"tool_call"} decodes to index 0; a frame {"event":"tool_call","index":0} round-trips with the key present -- two wire forms for the same logical value, and Python (index: int = 0) and Go (omitempty) each emit a third variant.

Question for the designer: Does the revised design intend ToolCallEvent.index to be required (always emitted, including 0) or optional (omitted at 0) in the openapi -- and if optional, why does Rust use #[serde(default)] WITHOUT skip_serializing_if (which makes it always serialize the key, unlike Go's omitempty and unlike the sibling Token variant), producing a three-way serialize-side mismatch that only a raw-bytes wire test, not a Rust-to-Rust round-trip test, would catch?

---

Lessons consulted: 5 (3 guardrail + 2 adversary-rejection general_note)
Step 0 query strings used:
  - search_lessons "llm gateway tool-use SSE streaming" --type guardrail --limit 10 --format json
  - search_lessons "streamer.go openapi SDK" --tags adversary-rejection --limit 5 --format json
Guardrails relevant: (none directly -- the 3 guardrails returned are git-push / force-push / DB-migration scope rules, not SSE/contract rules; informational context only)
Prior REJECTED patterns: rdy-rejected-test review-design REJECTED with 2 BLOCK on contract holes (informs Finding 2 -- D8's closed allowlist is a second, narrower contract hole replacing the round-1 one); amaw-task-slug-validation review-code REJECTED for a fix that closed only one of two entry points (informs Finding 1 -- D1's emit-rule fix lands at the parse layer but the omitempty serialize layer re-opens the same drop, a partial-closure pattern).
