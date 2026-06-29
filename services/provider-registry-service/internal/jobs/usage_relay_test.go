package jobs

// S4b — unit coverage for the usage-stream wire contract. The relay's DB-coupled
// paths (FinalizeWithUsageOutbox tx, drainOnce SELECT...FOR UPDATE SKIP LOCKED,
// XADD) are integration-only (jobs pkg has no DB harness) → D-S4B-RELAY-LIVE-SMOKE.
// This pins the field SHAPE that S4c (usage-billing) + S4d (campaign) parse, so a
// key rename / dropped field / type slip is caught without a live stack.

import "testing"

func TestBuildUsageFields_Contract(t *testing.T) {
	f := buildUsageFields("req-1", "owner-1", "camp-1", "mcpkey-1", "user_model", "model-1",
		"translation", "0.00012345", 120, 30)

	want := map[string]string{
		"request_id":     "req-1",
		"owner_user_id":  "owner-1",
		"campaign_id":    "camp-1",
		"mcp_key_id":     "mcpkey-1",
		"model_source":   "user_model",
		"model_ref":      "model-1",
		"operation":      "translation",
		"input_tokens":   "120",  // stringified
		"output_tokens":  "30",   // stringified
		"cost_usd":       "0.00012345",
		"request_status": "success", // constant
	}
	if len(f) != len(want) {
		t.Fatalf("field count: got %d want %d (%v)", len(f), len(want), f)
	}
	for k, v := range want {
		got, ok := f[k]
		if !ok {
			t.Fatalf("missing field %q", k)
		}
		if got != v {
			t.Fatalf("field %q: got %v want %q", k, got, v)
		}
	}
}

func TestBuildUsageFields_NullsArePassthroughEmpty(t *testing.T) {
	// A non-campaign job (campaign="") and a media/unpriced job (cost="") carry
	// empty strings — the consumer treats "" as null. Zero tokens stringify to "0".
	f := buildUsageFields("req-2", "owner-2", "", "", "platform_model", "model-2",
		"image_gen", "", 0, 0)
	if f["campaign_id"] != "" {
		t.Fatalf("campaign_id: want empty, got %v", f["campaign_id"])
	}
	if f["mcp_key_id"] != "" {
		t.Fatalf("mcp_key_id: want empty, got %v", f["mcp_key_id"])
	}
	if f["cost_usd"] != "" {
		t.Fatalf("cost_usd: want empty, got %v", f["cost_usd"])
	}
	if f["input_tokens"] != "0" || f["output_tokens"] != "0" {
		t.Fatalf("zero tokens must stringify to \"0\": %v / %v", f["input_tokens"], f["output_tokens"])
	}
}
