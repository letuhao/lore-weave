package api

import (
	"testing"

	"github.com/google/uuid"
)

// Real feedback repro (2026-07-08): an agent that discovers kg_*/memory_* tools under
// find_tools's "knowledge" GROUP naturally reuses that same string as confirm_action's
// `domain` arg — but the real routing key (DomainConfirmServiceURLs, /v1/<domain>/actions/confirm)
// is "kg", so the guess used to hit AUTH_CONFIRM_DOMAIN_UNROUTABLE for a perfectly valid token.
func TestNormalizeConfirmDomain(t *testing.T) {
	cases := map[string]string{
		"knowledge":   "kg",
		"kg":          "kg",
		"glossary":    "glossary",
		"composition": "composition",
		"":            "",
	}
	for in, want := range cases {
		if got := normalizeConfirmDomain(in); got != want {
			t.Errorf("normalizeConfirmDomain(%q) = %q, want %q", in, got, want)
		}
	}
}

// D-C-PRODUCER-OUTBOX — the mcp_approval owner notification is now written to the
// transactional outbox (in the approval tx) and relay-delivered. This pins the ingest
// body the relay POSTs, incl. the deterministic dedup_key that makes at-least-once
// delivery idempotent.
func TestApprovalNotificationBody(t *testing.T) {
	owner := uuid.New()
	approvalID := uuid.New()
	body := approvalNotificationBody(owner, approvalID, "book.propose_edit")

	if body["user_id"] != owner.String() {
		t.Errorf("user_id = %v, want %v", body["user_id"], owner.String())
	}
	if body["category"] != "mcp_approval" {
		t.Errorf("category = %v, want mcp_approval (P0-4: this was silently 400-dropped before)", body["category"])
	}
	if got := body["dedup_key"]; got != "mcp_approval:"+approvalID.String() {
		t.Errorf("dedup_key = %v, want mcp_approval:<approval_id>", got)
	}
	meta, ok := body["metadata"].(map[string]any)
	if !ok {
		t.Fatalf("metadata is not a map: %T", body["metadata"])
	}
	if meta["approval_id"] != approvalID.String() || meta["tool_name"] != "book.propose_edit" {
		t.Errorf("metadata = %v, want approval_id + tool_name", meta)
	}
	if body["title"] == "" || body["body"] == "" {
		t.Error("title and body must be non-empty (the English fallback render)")
	}
}

// Distinct approvals produce distinct dedup keys (not collapsed as duplicates).
func TestApprovalNotificationDedupKeyIsPerApproval(t *testing.T) {
	owner := uuid.New()
	a := approvalNotificationBody(owner, uuid.New(), "t")
	b := approvalNotificationBody(owner, uuid.New(), "t")
	if a["dedup_key"] == b["dedup_key"] {
		t.Error("two different approvals must not share a dedup_key")
	}
}
