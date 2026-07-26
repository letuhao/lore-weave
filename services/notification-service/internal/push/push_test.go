package push

import (
	"strings"
	"testing"
)

// B1 — the content-free chokepoint. BuildPayload must be a PURE function of the topic and must NEVER
// echo any title/body/PII. The structural guarantee is the signature (it accepts only a PushTopic);
// these tests assert the behavioural half: deterministic, drawn from the fixed set, and a payload
// built for a topic never contains a sample PII string that a producer's title/body might carry.
func TestBuildPayload_ContentFree_PureFunctionOfTopic(t *testing.T) {
	piiSamples := []string{"Priya", "auth module", "claude-test@loreweave.dev", "login bug", "Q3 roadmap"}

	for _, topic := range AllTopics {
		p1 := BuildPayload(topic)
		p2 := BuildPayload(topic)
		// deterministic
		if p1 != p2 {
			t.Errorf("topic %s: BuildPayload not deterministic: %v vs %v", topic, p1, p2)
		}
		// non-empty (never a blank lock-screen)
		if p1.Title == "" || p1.Body == "" {
			t.Errorf("topic %s: empty copy %+v", topic, p1)
		}
		// carries the topic token (for later localization), not content
		if p1.Topic != string(topic) {
			t.Errorf("topic %s: payload.Topic = %q", topic, p1.Topic)
		}
		// content-free: no PII sample can appear (the fixed strings contain none)
		for _, pii := range piiSamples {
			if strings.Contains(p1.Title, pii) || strings.Contains(p1.Body, pii) {
				t.Errorf("topic %s: payload leaked PII sample %q: %+v", topic, pii, p1)
			}
		}
	}
}

func TestBuildPayload_UnknownTopic_FallsBackToNeutralSystemCopy(t *testing.T) {
	p := BuildPayload(PushTopic("not-a-real-topic"))
	sys := BuildPayload(TopicSystem)
	if p.Title != sys.Title || p.Body != sys.Body {
		t.Errorf("unknown topic should fall back to system copy, got %+v", p)
	}
}

// H3 — the (category, message_key) → push_topic map, incl. the assistant subtype split and the
// unknown-subtype-safe-default.
func TestResolveTopic(t *testing.T) {
	cases := []struct {
		category, messageKey string
		want                 PushTopic
	}{
		{"assistant", "notif.assistant.reflection", TopicAssistantWeekly},
		{"assistant", "notif.assistant.proactive_checkin", TopicAssistantEndOfDay},
		{"assistant", "notif.assistant.some_new_subtype", TopicAssistantEndOfDay}, // safe default
		{"assistant", "", TopicAssistantEndOfDay},
		{"translation", "notif.translation.completed", TopicJobs},
		{"llm_job", "notif.llm_job.completed", TopicJobs},
		{"campaign", "notif.campaign.done", TopicJobs},
		{"billing", "notif.billing.near_cap", TopicBilling},
		{"social", "notif.social.follow", TopicSocial},
		{"mcp_approval", "notif.mcp_approval.request", TopicMcpApproval},
		{"system", "", TopicSystem},
		{"wiki", "", TopicSystem},
	}
	for _, c := range cases {
		if got := ResolveTopic(c.category, c.messageKey); got != c.want {
			t.Errorf("ResolveTopic(%q,%q) = %q, want %q", c.category, c.messageKey, got, c.want)
		}
	}
}

func TestTopicDefaults_SocialOffMcpOn(t *testing.T) {
	if TopicDefaults[TopicSocial] {
		t.Error("social must be push-OFF by default (opt-in)")
	}
	if !TopicDefaults[TopicMcpApproval] {
		t.Error("mcp_approval must be push-ON by default (security-sensitive)")
	}
	if TopicDefaults[TopicSystem] {
		t.Error("system must be in-app-only (no push by default)")
	}
}

func TestValidTopic(t *testing.T) {
	if !ValidTopic("jobs") || !ValidTopic("assistant_weekly") {
		t.Error("expected known topics valid")
	}
	if ValidTopic("bogus") || ValidTopic("") {
		t.Error("expected unknown topics invalid")
	}
}
