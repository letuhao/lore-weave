package jobs

// Phase 3b — per-operation result aggregator with multi-chunk support.
// Worker calls StartChunk/EndChunk around each adapter.Stream invocation
// when chunking is configured; for unchunked jobs neither hook fires
// and behavior is identical to Phase 2b.
//
// One Aggregator instance is created per job invocation. It owns
// mutable counter + accumulator state so the worker doesn't need to.
//
// Per-operation result schemas are documented (informally) in
// contracts/api/llm-gateway/v1/openapi.yaml under `Job.result`.

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

// chunkSeparator joins per-chunk content in the final aggregated
// result. Two newlines so adjacent chunks read as separate paragraphs;
// callers wanting raw concatenation can post-process.
const chunkSeparator = "\n\n"

// Aggregator collapses per-chunk StreamChunk events into a single result
// payload. Each operation has its own aggregator type; we expose one
// constructor that selects by operation name.
//
// Phase 3b lifecycle for a chunked job:
//
//	NewAggregator(op)
//	for each chunk:
//	    StartChunk(idx)
//	    for each StreamChunk: Accept(...)
//	    EndChunk(idx)
//	Finalize() → result
//
// Unchunked job (Phase 2b path): no Start/End calls; Accept/Finalize
// behave identically to before.
type Aggregator interface {
	// StartChunk signals a new chunk's stream is about to begin.
	// Aggregators that need per-chunk state reset their per-chunk
	// buffers here. idx is 0-based.
	StartChunk(idx int)

	// EndChunk signals the chunk's stream has completed cleanly.
	// Aggregators that defer cross-chunk merging until between-chunk
	// boundaries flush per-chunk state into global state here.
	EndChunk(idx int)

	// Accept consumes one StreamChunk. Returns true if the consumer
	// (worker) should also forward the chunk to a downstream sink (FE
	// progress) — Phase 2b ignores this; Phase 2c uses it to emit
	// per-token callbacks.
	Accept(chunk provider.StreamChunk) bool

	// Finalize returns the canonical result payload + final usage
	// counters once all chunks have been processed. The map shape
	// matches the openapi `Job.result` documentation per operation.
	Finalize() (result map[string]any, inputTokens int, outputTokens int)
}

// NewAggregator picks the right Aggregator implementation for the
// operation. Unknown operations get a generic accumulator that just
// concatenates token deltas into a single content string.
func NewAggregator(operation string) Aggregator {
	switch operation {
	case "chat", "completion":
		return &chatAggregator{}
	case "entity_extraction":
		return newJSONListAggregator("entities", entityKey)
	case "relation_extraction":
		return newJSONListAggregator("relations", relationKey)
	case "event_extraction":
		return newJSONListAggregator("events", eventKey)
	case "fact_extraction":
		return newJSONListAggregator("facts", factKey)
	default:
		return &chatAggregator{} // default to text-concat
	}
}

// entityKey produces a dedup key for entity rows. Same (name, kind)
// across chunks → keep highest-confidence entry. Aliases array, if
// present, is merged on tie.
func entityKey(e map[string]any) string {
	name, _ := e["name"].(string)
	kind, _ := e["kind"].(string)
	return name + "\x00" + kind
}

// relationKey dedups by (subject, predicate, object, polarity). Phase
// 4a knowledge-service uses this when chunks of one chapter are
// processed independently — the same relation surfacing in two
// adjacent chunks (overlap region) collapses to one.
func relationKey(r map[string]any) string {
	subj, _ := r["subject"].(string)
	pred, _ := r["predicate"].(string)
	obj, _ := r["object"].(string)
	polarity, _ := r["polarity"].(string)
	if polarity == "" {
		polarity = "affirm"
	}
	return subj + "\x00" + pred + "\x00" + obj + "\x00" + polarity
}

// eventKey dedups by (name, time_cue) — events with the same name at
// the same narrative cue are likely the same beat surfacing across
// adjacent chunks. Different cues → distinct events.
func eventKey(ev map[string]any) string {
	name, _ := ev["name"].(string)
	cue, _ := ev["time_cue"].(string)
	return name + "\x00" + cue
}

// factKey dedups by (type, normalized content). Phase 4a-β knowledge-
// service emits facts as `{content, type, subject?, polarity, modality,
// confidence}`. Two chunks restating the same factual claim ("Holmes
// is a detective") collapse to one row; differently-typed claims about
// the same content stay distinct ("type: trait" vs "type: profession").
//
// Polarity is INTENTIONALLY EXCLUDED from the key — contradicting
// polarities (affirm/negate) of the same content COLLAPSE to a single
// row (last-writer-wins on polarity). This matches knowledge-service's
// `_postprocess` which derives fact_id from content alone, so the two
// layers stay consistent end-to-end. Conflict detection is downstream's
// concern — Pass 2 writer or future quality-eval can flag content with
// observed polarity flips by querying the raw chunk emissions in
// telemetry; the aggregated row only carries the latest verdict.
// (Adding polarity to the key would surface contradictions but would
// require a matching change to Python's `_normalize_content` + a
// fact_id schema migration — out of scope for 4a-β; tracked as
// D-PHASE6-FACT-POLARITY-IN-KEY.)
//
// Subject is also excluded because facts can be subject-less (universal
// claims) and the same factual content emitted with vs. without a
// subject in different chunks should dedup to the higher-confidence
// variant. Note: when winner emits subject=null and loser emits
// subject=<name>, the merged row currently keeps null (winner wins) —
// see D-PHASE6-AGGREGATOR-NULL-MERGE.
//
// Content is whitespace-collapsed + lowercased to mirror knowledge-
// service's `_normalize_content` (services/knowledge-service/app/
// extraction/llm_fact_extractor.py:_normalize_content) so a chunk
// emitting "Holmes  is a  detective" matches "Holmes is a detective".
func factKey(f map[string]any) string {
	content, _ := f["content"].(string)
	factType, _ := f["type"].(string)
	return factType + "\x00" + normalizeFactContent(content)
}

// normalizeFactContent lowercases + collapses internal whitespace runs
// to single spaces. Mirrors knowledge-service's `_normalize_content`
// helper so the gateway-side dedup matches caller-side fact_id hashing.
func normalizeFactContent(s string) string {
	return strings.Join(strings.Fields(strings.ToLower(s)), " ")
}

// chatAggregator accumulates token deltas + reasoning + usage with
// multi-chunk awareness.
//
// Per-chunk state:
//   - chunkContent: tokens for the CURRENT chunk; flushed to globalTokens
//     on EndChunk with chunkSeparator between non-empty chunks.
//   - chunkReasoning: reasoning for the CURRENT chunk; the LAST chunk's
//     reasoning wins (typical thinking-model UX where the final answer's
//     synthesis is the value-add, not earlier draft thoughts).
//
// Global state (across chunks):
//   - globalTokens: final concatenated content.
//   - lastReasoning: most-recent finished chunk's reasoning.
//   - input/output/reasoningTokens: SUMMED across chunks for billing.
//   - finishReason: last chunk's finish reason wins (caller drives
//     order; the streamer emits done last).
type chatAggregator struct {
	// Global, cross-chunk
	globalTokens    strings.Builder
	lastReasoning   string
	inputTokens     int
	outputTokens    int
	reasoningTokens int
	finishReason    string
	chunkCount      int

	// Per-chunk (reset on StartChunk; flushed on EndChunk)
	chunkContent   strings.Builder
	chunkReasoning strings.Builder
	inChunk        bool
}

func (a *chatAggregator) StartChunk(_ int) {
	a.inChunk = true
	a.chunkContent.Reset()
	a.chunkReasoning.Reset()
}

func (a *chatAggregator) EndChunk(_ int) {
	if !a.inChunk {
		return
	}
	a.inChunk = false
	piece := a.chunkContent.String()
	if piece != "" {
		if a.chunkCount > 0 {
			a.globalTokens.WriteString(chunkSeparator)
		}
		a.globalTokens.WriteString(piece)
	}
	if a.chunkReasoning.Len() > 0 {
		a.lastReasoning = a.chunkReasoning.String()
	}
	a.chunkCount++
}

func (a *chatAggregator) Accept(chunk provider.StreamChunk) bool {
	switch chunk.Kind {
	case provider.StreamChunkToken:
		// Route into the per-chunk buffer when chunked, else straight
		// to the global builder so unchunked Phase 2b behavior is
		// preserved with no Start/End calls.
		if a.inChunk {
			a.chunkContent.WriteString(chunk.Delta)
		} else {
			a.globalTokens.WriteString(chunk.Delta)
		}
	case provider.StreamChunkReasoning:
		if a.inChunk {
			a.chunkReasoning.WriteString(chunk.Delta)
		} else {
			// Unchunked path keeps reasoning in lastReasoning so
			// Finalize() emits it as before.
			a.lastReasoning += chunk.Delta
		}
	case provider.StreamChunkUsage:
		// Sum across chunks. inputTokens for chunked jobs is the SUM
		// of each chunk's prompt tokens (each chunk re-pays the system
		// prompt + chunk content); outputTokens is the SUM of each
		// chunk's generated tokens.
		a.inputTokens += chunk.InputTokens
		a.outputTokens += chunk.OutputTokens
		if chunk.ReasoningTokens != nil {
			a.reasoningTokens += *chunk.ReasoningTokens
		}
	case provider.StreamChunkDone:
		a.finishReason = chunk.FinishReason
	case provider.StreamChunkError:
		// Errors are surfaced via Finalize → worker → repo.Finalize();
		// nothing to accumulate here.
	}
	return true
}

func (a *chatAggregator) Finalize() (map[string]any, int, int) {
	// If we're still inside a chunk (caller forgot EndChunk), flush
	// defensively. Belt-and-braces.
	if a.inChunk {
		a.EndChunk(-1)
	}
	message := map[string]any{
		"role":    "assistant",
		"content": a.globalTokens.String(),
	}
	if a.lastReasoning != "" {
		message["reasoning_content"] = a.lastReasoning
	}
	usage := map[string]any{
		"input_tokens":  a.inputTokens,
		"output_tokens": a.outputTokens,
	}
	if a.reasoningTokens > 0 {
		usage["reasoning_tokens"] = a.reasoningTokens
	}
	result := map[string]any{
		"messages": []any{message},
		"usage":    usage,
	}
	if a.finishReason != "" {
		result["finish_reason"] = a.finishReason
	}
	return result, a.inputTokens, a.outputTokens
}

// jsonListAggregator collects token deltas into per-chunk JSON-string
// buffers, parses each chunk on EndChunk, and merges the named list
// field by a caller-supplied dedup key. Used by entity / relation /
// event extraction operations that all return `{<list_field>: [...]}`
// shaped JSON.
//
// Soft-fail design: a chunk whose buffer parses as invalid JSON
// contributes no items but doesn't fail the whole job — its error is
// captured in the result envelope's `errors` array so the caller can
// see partial-extraction quality. This matches the Phase 4a goal of
// "knowledge-service should still complete a chapter even if one
// chunk's LLM output was malformed".
type jsonListAggregator struct {
	listField string
	keyFn     func(map[string]any) string

	// Per-chunk
	chunkBuffer strings.Builder
	inChunk     bool

	// Cross-chunk
	merged          map[string]map[string]any // dedup key → row
	order           []string                  // preserve insertion order
	chunkErrors     []string
	inputTokens     int
	outputTokens   int
	reasoningTokens int
	finishReason    string
}

func newJSONListAggregator(field string, keyFn func(map[string]any) string) *jsonListAggregator {
	return &jsonListAggregator{
		listField: field,
		keyFn:     keyFn,
		merged:    map[string]map[string]any{},
	}
}

func (a *jsonListAggregator) StartChunk(_ int) {
	a.inChunk = true
	a.chunkBuffer.Reset()
}

func (a *jsonListAggregator) EndChunk(idx int) {
	if !a.inChunk {
		return
	}
	a.inChunk = false
	raw := a.chunkBuffer.String()
	a.chunkBuffer.Reset() // Belt: prevents Finalize defensive-flush from re-parsing.
	if raw == "" {
		return
	}
	a.mergeChunkJSON(idx, raw)
}

// Accept routes Token deltas into the per-chunk buffer (chunked) or
// directly into a shared buffer (unchunked Phase 2b backward-compat).
// Reasoning is captured for billing tokens only — extraction ops
// don't surface reasoning_content (the parsed result is the value-add).
func (a *jsonListAggregator) Accept(chunk provider.StreamChunk) bool {
	switch chunk.Kind {
	case provider.StreamChunkToken:
		// Both chunked + unchunked paths write to chunkBuffer; the
		// distinction is whether StartChunk/EndChunk frames the parse,
		// or Finalize handles a single trailing parse for unchunked.
		a.chunkBuffer.WriteString(chunk.Delta)
	case provider.StreamChunkReasoning:
		// Extraction-op reasoning is not surfaced; only count tokens.
	case provider.StreamChunkUsage:
		a.inputTokens += chunk.InputTokens
		a.outputTokens += chunk.OutputTokens
		if chunk.ReasoningTokens != nil {
			a.reasoningTokens += *chunk.ReasoningTokens
		}
	case provider.StreamChunkDone:
		a.finishReason = chunk.FinishReason
	case provider.StreamChunkError:
		// Errors surface via worker → repo.Finalize, not here.
	}
	return true
}

// mergeChunkJSON parses a chunk's JSON output and merges its list
// items into `merged` keyed by keyFn. Tie-break: keep highest
// confidence; on equal confidence, first writer wins (insertion
// order preserved via `order` slice).
func (a *jsonListAggregator) mergeChunkJSON(idx int, raw string) {
	var parsed map[string]any
	if err := json.Unmarshal([]byte(raw), &parsed); err != nil {
		a.chunkErrors = append(a.chunkErrors,
			fmt.Sprintf("chunk %d: %s", idx, err.Error()))
		return
	}
	rawList, ok := parsed[a.listField].([]any)
	if !ok {
		a.chunkErrors = append(a.chunkErrors,
			fmt.Sprintf("chunk %d: missing or non-array %q field", idx, a.listField))
		return
	}
	for _, item := range rawList {
		row, ok := item.(map[string]any)
		if !ok {
			continue
		}
		key := a.keyFn(row)
		existing, dup := a.merged[key]
		if !dup {
			a.merged[key] = row
			a.order = append(a.order, key)
			continue
		}
		// Tie-break by confidence — keep higher value's row, but merge
		// any keys the existing row has that the new row doesn't (e.g.
		// aliases that surfaced in chunk 0 but not chunk 2).
		newConf := floatOrZero(row["confidence"])
		oldConf := floatOrZero(existing["confidence"])
		// `mergeKnownKeys(winner, loser)` — winner's keys take
		// precedence; loser fills in fields the winner doesn't have.
		// Higher confidence wins; on tie, existing (insertion-order
		// first) wins.
		if newConf > oldConf {
			a.merged[key] = mergeKnownKeys(row, existing)
		} else {
			a.merged[key] = mergeKnownKeys(existing, row)
		}
	}
}

// mergeKnownKeys returns a copy of `winner` with any keys present in
// `loser` (but missing from `winner`) carried over.
//
// /review-impl Phase 4a-β MED#2 fix — non-null preference: when winner
// has a key with a NULL value AND loser has the same key with a non-null
// value, prefer loser's non-null. Without this, fact_extraction's
// nullable `subject` field would silently lose data: chunk A emits
// {content:"X", subject:null, conf:0.95} + chunk B emits {content:"X",
// subject:"Holmes", conf:0.9} → A wins by confidence → merged subject
// stays null and Holmes attribution is lost. This rule is generally
// safe across ops because winner-selection is by confidence, not by
// completeness — a higher-confidence row that omitted a field shouldn't
// erase a lower-confidence row's contribution.
//
// The "aliases" key still gets union semantic when both rows have it.
func mergeKnownKeys(winner, loser map[string]any) map[string]any {
	out := make(map[string]any, len(winner))
	for k, v := range winner {
		out[k] = v
	}
	for k, v := range loser {
		if _, has := out[k]; !has {
			out[k] = v
			continue
		}
		// Aliases: union the two arrays preserving order.
		if k == "aliases" {
			out[k] = unionStringList(out[k], v)
			continue
		}
		// MED#2 — winner-null + loser-non-null → prefer loser.
		if out[k] == nil && v != nil {
			out[k] = v
		}
	}
	return out
}

func unionStringList(a, b any) []any {
	seen := map[string]bool{}
	var out []any
	add := func(v any) {
		s, ok := v.(string)
		if !ok {
			return
		}
		if !seen[s] {
			seen[s] = true
			out = append(out, s)
		}
	}
	if al, ok := a.([]any); ok {
		for _, v := range al {
			add(v)
		}
	}
	if bl, ok := b.([]any); ok {
		for _, v := range bl {
			add(v)
		}
	}
	return out
}

func floatOrZero(v any) float64 {
	switch x := v.(type) {
	case float64:
		return x
	case int:
		return float64(x)
	case int64:
		return float64(x)
	}
	return 0
}

func (a *jsonListAggregator) Finalize() (map[string]any, int, int) {
	// Defensive flush: caller forgot EndChunk before Finalize. Treat
	// the trailing buffer as the implicit last chunk (or the only
	// chunk in unchunked-mode where StartChunk was never called).
	if a.inChunk || (len(a.merged) == 0 && a.chunkBuffer.Len() > 0) {
		a.mergeChunkJSON(len(a.order), a.chunkBuffer.String())
		a.inChunk = false
		a.chunkBuffer.Reset()
	}
	items := make([]any, 0, len(a.order))
	for _, k := range a.order {
		items = append(items, a.merged[k])
	}
	usage := map[string]any{
		"input_tokens":  a.inputTokens,
		"output_tokens": a.outputTokens,
	}
	if a.reasoningTokens > 0 {
		usage["reasoning_tokens"] = a.reasoningTokens
	}
	result := map[string]any{
		a.listField: items,
		"usage":     usage,
	}
	if a.finishReason != "" {
		result["finish_reason"] = a.finishReason
	}
	if len(a.chunkErrors) > 0 {
		result["chunk_errors"] = a.chunkErrors
	}
	return result, a.inputTokens, a.outputTokens
}

