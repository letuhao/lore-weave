package provider

import (
	"bytes"
	"encoding/json"
)

// openai_content_policy.go — Phase 5d /review-impl(DESIGN) Fix #4
// refactor. Shared content-policy detection helper, originally in
// openai_image.go (Phase 5c-α). Now used by both image_gen and
// video_gen adapters; centralized to avoid drift if the heuristic
// needs to evolve.
//
// No behavior change vs. Phase 5c-α implementation. Existing image
// content-policy tests (TestOpenAIAdapter_GenerateImage_ContentPolicy_*)
// continue to cover the helper unchanged.

// isContentPolicyRejection detects DALL-E / gpt-image-1 / safety-system
// content-policy errors. OpenAI returns:
//
//	{"error": {"code": "content_policy_violation", "type": "image_generation_user_error", ...}}
//
// for safety blocks. Status is typically 400 but sometimes 403 or
// even 200-with-error-field.
//
// /review-impl(Phase 5c-α DESIGN) MED#3 — JSON-FIRST. The prior
// substring-only heuristic would false-positive when upstream echoes
// the user's prompt back in the error body (e.g., "your prompt 'X
// content_policy_violation Y' rejected for…"). Structural JSON check
// on error.code is authoritative when the body parses as JSON;
// substring fallback only fires for non-JSON bodies (HTML error pages
// from misconfigured upstreams).
//
// Shared between image_gen and video_gen — local-image-generator-service
// uses the same error shape for both endpoints, and managed services
// (OpenAI, future Sora-compat) follow the same pattern.
func isContentPolicyRejection(status int, body []byte) bool {
	var parsed struct {
		Error struct {
			Code string `json:"code"`
			Type string `json:"type"`
		} `json:"error"`
	}
	if err := json.Unmarshal(body, &parsed); err == nil {
		// JSON parsed successfully — error.code is authoritative.
		switch parsed.Error.Code {
		case "content_policy_violation", "moderation_blocked":
			return true
		}
		if parsed.Error.Type == "image_generation_user_error" {
			return true
		}
		// JSON parsed but no policy marker — definitively NOT a policy
		// rejection; do NOT fall through to substring (avoids the
		// prompt-echo false-positive).
		return false
	}
	// JSON parse failed → non-JSON body. Substring fallback gated by
	// high-signal status codes only.
	if status != 400 && status != 403 {
		return false
	}
	return bytes.Contains(body, []byte("content_policy_violation")) ||
		bytes.Contains(body, []byte("safety_system"))
}
