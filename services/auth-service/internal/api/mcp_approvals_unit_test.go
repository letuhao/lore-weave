package api

import (
	"testing"

	"github.com/google/uuid"
)

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
