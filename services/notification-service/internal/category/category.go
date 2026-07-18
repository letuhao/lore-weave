// Package category is the SINGLE source-of-truth for the notification
// category enum. Both notification ingress paths — the HTTP
// createNotification/createNotificationBatch handlers (internal/api) AND
// the AMQP terminal-event consumer (internal/consumer) — validate against
// this same set, so a category valid on one path is valid on the other.
//
// Root cause this fixes (audit P0-4 / NOTIF-2): the HTTP handler's local
// allow-list only covered {translation, social, wiki, system}, so real
// producers sending `mcp_approval` (auth-service) got a 400 that the
// producer's fire-and-forget goroutine silently swallowed — the
// notification was never persisted. Meanwhile the consumer inserted
// `llm_job` via raw SQL, bypassing validation entirely. Centralising the
// enum here and routing BOTH paths through Valid() closes the drift.
package category

// Allowed is the closed set of notification categories every producer in
// the platform legitimately emits. Keep this list exhaustive — a new
// producer category MUST be added here (and only here), never re-invented
// as a second local allow-list.
//
//	translation  — translation-service chapter worker
//	social       — auth-service follow / social events
//	wiki         — glossary-service wiki feature
//	system       — generic/authoring (composition-service, defaults)
//	llm_job      — the AMQP consumer (provider-registry job terminal events)
//	mcp_approval — auth-service MCP approval requests
//	campaign     — campaign-service run notifications
//	billing      — usage-billing-service spend/quota notifications
var Allowed = map[string]bool{
	"translation":  true,
	"social":       true,
	"wiki":         true,
	"system":       true,
	"llm_job":      true,
	"mcp_approval": true,
	"campaign":     true,
	"billing":      true,
	// R3 (D-PROACTIVE-DELIVERY) — the work-assistant proactive check-in (chat-service). Its own
	// category so a user can opt out of assistant pings without silencing every system notification
	// (Suppressed() keys on category — the per-category opt-out granularity).
	"assistant": true,
}

// Valid reports whether c is a recognised notification category. Both
// ingress paths call this so validation is identical on each.
func Valid(c string) bool {
	return Allowed[c]
}
