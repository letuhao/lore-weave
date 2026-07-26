package api

// usage_logging.go — P0-2 (enterprise-hardening audit, Area 1). Shared helpers for
// the full request/response logging on the SYNCHRONOUS provider-registry paths
// (streaming chat + sync embed/rerank/web-search). The async jobs path already logs
// full payloads via usage_outbox; these paths route through the same usage-record
// contract (billing.RecordUsage → usage-billing /internal/model-billing/record, which
// encrypts the payloads at rest with its dedicated KEK).

import (
	"encoding/json"
	"os"
	"strconv"
	"unicode/utf8"
)

// usagePayloadCapBytes bounds a single audit payload (request OR response) so a huge
// request (a 100K-token context) or response (a big embed batch) is logged by
// reference rather than shipped inline to usage-billing. Mirrors the async jobs
// path's LLM_USAGE_PAYLOAD_CAP_BYTES knob (same env var, same 16 KiB default).
var usagePayloadCapBytes = func() int {
	if v := os.Getenv("LLM_USAGE_PAYLOAD_CAP_BYTES"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			return n
		}
	}
	return 16384
}()

// boundedPayload returns m unchanged when its JSON encoding fits within the cap;
// otherwise it returns a compact reference stub (reference-first for huge payloads).
// nil in → nil out (billing.RecordUsage then omits the field entirely).
func boundedPayload(m map[string]any) map[string]any {
	if m == nil {
		return nil
	}
	b, err := json.Marshal(m)
	if err != nil {
		return map[string]any{"_unserializable": true}
	}
	if len(b) <= usagePayloadCapBytes {
		return m
	}
	// Reference stub: keep a small UTF-8-safe preview + the original byte size so a
	// trace can still show what the call looked like without carrying the whole blob.
	const previewMax = 512
	preview := b
	if len(preview) > previewMax {
		cut := previewMax
		for cut > 0 && !utf8.RuneStart(preview[cut]) {
			cut--
		}
		preview = preview[:cut]
	}
	return map[string]any{
		"_truncated": true,
		"_bytes":     len(b),
		"_preview":   string(preview),
	}
}
