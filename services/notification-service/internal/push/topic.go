// Package push implements the M5 Web Push delivery leg (D-MOB-4): the content-free lock-screen
// copy (B1), the category→topic mapping (H3), and the VAPID sender. Kept separate from the in-app
// notification path so the "no PII on the lock screen" chokepoint is one small, auditable unit.
package push

import "strings"

// PushTopic is a user-facing push toggle (the 7 the mobile settings show). It is NOT the raw
// notification category — the sender maps (category, message_key) → topic via ResolveTopic, and the
// user's push_preferences row (keyed by topic) decides whether to buzz.
type PushTopic string

const (
	TopicAssistantWeekly   PushTopic = "assistant_weekly"
	TopicAssistantEndOfDay PushTopic = "assistant_endofday"
	TopicJobs              PushTopic = "jobs"
	TopicBilling           PushTopic = "billing"
	TopicSocial            PushTopic = "social"
	TopicMcpApproval       PushTopic = "mcp_approval"
	TopicSystem            PushTopic = "system"
)

// TopicDefaults — the push-on-by-default per topic when the user has no push_preferences row (§1a).
// social is OFF (low-signal, opt-in); system/wiki is in-app-only (no push by default); mcp_approval
// is ON (a pending approval is security-sensitive and must reach the owner).
var TopicDefaults = map[PushTopic]bool{
	TopicAssistantWeekly:   true,
	TopicAssistantEndOfDay: true,
	TopicJobs:              true,
	TopicBilling:           true,
	TopicSocial:            false,
	TopicMcpApproval:       true,
	TopicSystem:            false,
}

// AllTopics is the closed set (for validating a client's toggle write — Settings-Boundary enum-close).
var AllTopics = []PushTopic{
	TopicAssistantWeekly, TopicAssistantEndOfDay, TopicJobs, TopicBilling,
	TopicSocial, TopicMcpApproval, TopicSystem,
}

// ValidTopic reports whether t is a recognised push topic.
func ValidTopic(t string) bool {
	for _, a := range AllTopics {
		if string(a) == t {
			return true
		}
	}
	return false
}

// ResolveTopic maps a stored notification's (category, message_key) to its push_topic (§1a/H3).
// The `assistant` category splits into weekly vs end-of-day by message_key; an UNKNOWN assistant
// subtype falls back to the safer on-by-default end-of-day bucket, so a newly-added subtype is never
// silently un-pushable. "jobs" spans translation/llm_job/campaign. Anything else (system, wiki) maps
// to the in-app-only system topic.
func ResolveTopic(category, messageKey string) PushTopic {
	switch category {
	case "assistant":
		if strings.Contains(messageKey, "reflection") {
			return TopicAssistantWeekly
		}
		return TopicAssistantEndOfDay
	case "translation", "llm_job", "campaign":
		return TopicJobs
	case "billing":
		return TopicBilling
	case "social":
		return TopicSocial
	case "mcp_approval":
		return TopicMcpApproval
	default:
		return TopicSystem
	}
}
