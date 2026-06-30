package api

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/loreweave/observability"
)

// translationHTTPClient is shared across snapshot-translation fills. Unlike bookHTTPClient (5 s),
// this calls translation-service's translate-text which performs a real LLM round-trip, so the
// timeout is generous (120 s). Traced transport → outbound CLIENT span + W3C traceparent.
var translationHTTPClient = &http.Client{Timeout: 120 * time.Second, Transport: observability.HTTPTransport(nil)}

// translateText asks translation-service to translate one bounded free-text string ON BEHALF OF
// userID (mirrors knowledge-service's KG-TL M3 TranslationClient). The actual MT resolves the
// user's BYOK translation model via provider-registry inside translation-service —
// glossary never imports a provider SDK (provider-gateway invariant).
//
// Returns (translatedText, errCode). errCode == "" ⇒ success. On any failure errCode is a stable,
// FE-facing token: "unconfigured" (no TRANSLATION_SERVICE_URL), "no_model" (422 — user has no
// translation model), "quota" (402), "provider" (any other non-200 / transport / decode error).
// Never panics; degrade-safe.
func (s *Server) translateText(ctx context.Context, userID, text, sourceLang, targetLang string) (string, string) {
	base := strings.TrimRight(s.cfg.TranslationServiceURL, "/")
	if base == "" {
		return "", "unconfigured"
	}
	if sourceLang == "" {
		sourceLang = "auto"
	}
	payload, err := json.Marshal(map[string]any{
		"user_id":         userID,
		"text":            text,
		"source_language": sourceLang,
		"target_language": targetLang,
	})
	if err != nil {
		return "", "provider"
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		base+"/internal/translation/translate-text", bytes.NewReader(payload))
	if err != nil {
		return "", "provider"
	}
	req.Header.Set("Content-Type", "application/json")
	if s.cfg.InternalServiceToken != "" {
		req.Header.Set("X-Internal-Token", s.cfg.InternalServiceToken)
	}
	if tid := TraceIDFromContext(ctx); tid != "" {
		req.Header.Set(traceIDHeader, tid)
	}
	res, err := translationHTTPClient.Do(req)
	if err != nil {
		return "", "provider"
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		switch res.StatusCode {
		case http.StatusUnprocessableEntity: // 422 — TRANSL_NO_MODEL_CONFIGURED
			return "", "no_model"
		case http.StatusPaymentRequired: // 402 — quota/credits exhausted
			return "", "quota"
		default:
			return "", "provider"
		}
	}
	var body struct {
		TranslatedText string `json:"translated_text"`
	}
	if err := json.NewDecoder(res.Body).Decode(&body); err != nil {
		return "", "provider"
	}
	out := strings.TrimSpace(body.TranslatedText)
	if out == "" {
		return "", "provider"
	}
	return out, ""
}
