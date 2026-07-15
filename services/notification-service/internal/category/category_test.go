package category

import "testing"

// TestValid_AcceptsEveryProducerCategory locks the single source-of-truth
// enum: every category a real platform producer emits MUST be accepted.
// The regression this guards (audit P0-4): mcp_approval was NOT in the
// original {translation, social, wiki, system} allow-list, so auth-service
// MCP-approval notifications got a 400 that the producer silently swallowed.
func TestValid_AcceptsEveryProducerCategory(t *testing.T) {
	for _, c := range []string{
		"translation",  // translation-service chapter worker
		"social",       // auth-service follow events
		"wiki",         // glossary-service wiki
		"system",       // composition-service / defaults
		"llm_job",      // the AMQP consumer
		"mcp_approval", // auth-service MCP approvals — the P0-4 regression
		"campaign",     // campaign-service
		"billing",      // usage-billing-service
		"assistant",    // chat-service proactive check-in (R3 / D-PROACTIVE-DELIVERY)
	} {
		if !Valid(c) {
			t.Errorf("category %q must be accepted (real producers emit it)", c)
		}
	}
}

func TestValid_RejectsUnknown(t *testing.T) {
	for _, c := range []string{"", "bogus", "Translation", "llm-job", "approval"} {
		if Valid(c) {
			t.Errorf("category %q must be rejected", c)
		}
	}
}
