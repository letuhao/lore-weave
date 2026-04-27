package jobs

// chunked_input.go — Phase 3c. Pure-function helpers that turn a single
// chat input + a list of chunked text pieces into N per-chunk inputs
// the Worker hands to adapter.Stream one at a time.
//
// The convention for chat ops: the LAST user message's `content` is
// what gets chunked. System prompts + earlier turns repeat verbatim
// in every per-chunk input. This matches the typical "summarize this
// long doc" / "translate this long text" use case where the long text
// is the user's most recent ask.

import (
	"encoding/json"
	"fmt"
)

// ChunkConfig mirrors the openapi ChunkingConfig. Decoded from the
// llm_jobs.chunking JSONB column at job dispatch time.
type ChunkConfig struct {
	Strategy string `json:"strategy"`
	Size     int    `json:"size,omitempty"`
	Overlap  int    `json:"overlap,omitempty"`
}

// DecodeChunkConfig pulls a ChunkConfig out of the JSONB blob stored
// on the row. Empty/null returns nil so the caller can branch on
// "no chunking requested".
func DecodeChunkConfig(raw json.RawMessage) (*ChunkConfig, error) {
	if len(raw) == 0 || string(raw) == "null" {
		return nil, nil
	}
	var c ChunkConfig
	if err := json.Unmarshal(raw, &c); err != nil {
		return nil, fmt.Errorf("decode chunking: %w", err)
	}
	if c.Strategy == "" || c.Strategy == "none" {
		return nil, nil
	}
	return &c, nil
}

// ExtractChattableText finds the user-supplied text the chunker should
// split. For chat-shaped input it returns the LAST user message's
// `content` string. Returns ("", false) if the input shape doesn't
// match (e.g. tools-only request, embedding op, etc.) so the caller
// can fall back to single-chunk mode.
func ExtractChattableText(input map[string]any) (string, bool) {
	msgs, ok := input["messages"].([]any)
	if !ok || len(msgs) == 0 {
		return "", false
	}
	// Walk backwards to find the most recent user message.
	for i := len(msgs) - 1; i >= 0; i-- {
		m, ok := msgs[i].(map[string]any)
		if !ok {
			continue
		}
		role, _ := m["role"].(string)
		if role != "user" {
			continue
		}
		content, ok := m["content"].(string)
		if !ok || content == "" {
			return "", false
		}
		return content, true
	}
	return "", false
}

// SubstituteLastUserMessage returns a deep-enough copy of `input` where
// the last user message's `content` has been replaced with `chunk`.
// The copy is a new top-level map + a new messages slice, but message
// objects are shallow-cloned only for the one we mutate (other
// messages reference the original maps — safe because we never
// mutate them).
func SubstituteLastUserMessage(input map[string]any, chunk string) (map[string]any, error) {
	out := make(map[string]any, len(input))
	for k, v := range input {
		out[k] = v
	}
	srcMsgs, ok := input["messages"].([]any)
	if !ok || len(srcMsgs) == 0 {
		return nil, fmt.Errorf("input.messages not found or empty")
	}
	dstMsgs := make([]any, len(srcMsgs))
	copy(dstMsgs, srcMsgs)

	// Find the last user message and shallow-clone it before mutation.
	for i := len(dstMsgs) - 1; i >= 0; i-- {
		m, ok := dstMsgs[i].(map[string]any)
		if !ok || m["role"] != "user" {
			continue
		}
		clone := make(map[string]any, len(m))
		for k, v := range m {
			clone[k] = v
		}
		clone["content"] = chunk
		dstMsgs[i] = clone
		break
	}
	out["messages"] = dstMsgs
	return out, nil
}
