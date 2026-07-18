package push

// Payload is the CONTENT-FREE notification shown on a locked device. The load-bearing privacy
// invariant of the whole push leg (§8-B1): it is built EXCLUSIVELY from the push_topic — BuildPayload
// takes only a PushTopic and CANNOT read the notification row's title/body (which legitimately carry
// names/PII, because redact.Body scrubs secrets, not PII). A static per-topic phrase is the only
// thing that keeps diary/PII text off the lock screen for EVERY producer, present and future.
//
// The route hint + opaque notification id (for notificationclick deep-linking, §8-S5) are attached by
// the SENDER as `data`, never as visible title/body, and carry no content either.
type Payload struct {
	Title string `json:"title"`
	Body  string `json:"body"`
	// Topic lets a locale-aware service worker localize later; it is an enum token, not content.
	Topic string `json:"topic"`
}

// pushCopy — the fixed per-topic strings. Content-free by construction: a constant phrase per topic,
// no interpolation of any row field. English for now; localization is a follow-on (the payload
// carries `topic` so the SW could map it to a localized string).
var pushCopy = map[PushTopic]struct{ title, body string }{
	TopicAssistantWeekly:   {"Your weekly reflection is ready", "Open the assistant to review your week."},
	TopicAssistantEndOfDay: {"Your assistant has an update", "Open the assistant to see what's new."},
	TopicJobs:              {"A task finished", "One of your background jobs is done."},
	TopicBilling:           {"Billing update", "There's an update about your usage or spend."},
	TopicSocial:            {"New activity", "You have new activity on LoreWeave."},
	TopicMcpApproval:       {"Approval needed", "An agent is requesting your approval."},
	TopicSystem:            {"LoreWeave", "You have a new notification."},
}

// BuildPayload returns the content-free lock-screen copy for a topic. PURE function of the topic —
// it accepts NO title/body/params, so a PII leak is impossible by construction. An unrecognised topic
// falls back to the neutral system copy (never empty, never PII).
func BuildPayload(topic PushTopic) Payload {
	c, ok := pushCopy[topic]
	if !ok {
		c = pushCopy[TopicSystem]
	}
	return Payload{Title: c.title, Body: c.body, Topic: string(topic)}
}
