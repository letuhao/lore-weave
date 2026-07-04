// Package redact scrubs secret-shaped tokens from notification text before it is
// persisted or pushed. Both ingress paths (HTTP createNotification + the AMQP
// terminal-event consumer) route body text through Body() so a provider/system
// error message that echoed a credential can't land in the notifications table or
// the user's push feed.
//
// Scope is deliberately NARROW — only high-confidence SECRET shapes (bearer tokens,
// sk-/api-key strings). It does NOT touch emails or names: those are frequently
// LEGITIMATE in a notification body ("shared with a@b.com"), so redacting them
// would corrupt real content. This mirrors the Python loreweave_obs RedactFilter's
// secret patterns (one idiom fleet-wide), not a general PII scrubber.
package redact

import "regexp"

const mask = "[REDACTED]"

// Ordered longest-match-first so an "Authorization: Bearer sk-…" collapses to one
// mask rather than leaving a fragment. Case-insensitive on the label.
var patterns = []*regexp.Regexp{
	// Authorization: Bearer <token>  /  Bearer <token>
	regexp.MustCompile(`(?i)bearer\s+[A-Za-z0-9._\-]+`),
	// OpenAI-style keys: sk-… / sk-proj-… (min length avoids masking the bare word "sk")
	regexp.MustCompile(`(?i)sk-[A-Za-z0-9_\-]{16,}`),
	// generic api key: api[_-]?key = / : <value>
	regexp.MustCompile(`(?i)api[_-]?key["']?\s*[:=]\s*["']?[A-Za-z0-9._\-]{8,}`),
}

// Body returns s with any secret-shaped token replaced by [REDACTED]. Empty in →
// empty out. Safe to call on every message (cheap; no allocation when nothing
// matches, since ReplaceAll returns the original when there is no match).
func Body(s string) string {
	if s == "" {
		return s
	}
	for _, re := range patterns {
		s = re.ReplaceAllString(s, mask)
	}
	return s
}
