package api

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

// C6 / SD-C6 — the spend LANE derivation + priced voice cost. A voice_stt record lands in the
// 'assistant' lane WITH the real cost (total_cost_usd honoured); a chat record lands in 'interactive'.
func TestRecordInvocation_LaneAndVoiceCost_DB(t *testing.T) {
	pool := openGuardrailTestDB(t)
	srv := newGuardrailServer(t, pool)
	owner := uuid.New()

	record := func(purpose string, cost *float64) uuid.UUID {
		reqID := uuid.New()
		body := map[string]any{
			"request_id": reqID, "owner_user_id": owner, "model_ref": uuid.New(),
			"provider_kind": "lm_studio", "model_source": "user_model",
			"input_tokens": 0, "output_tokens": 0, "purpose": purpose,
		}
		if cost != nil {
			body["total_cost_usd"] = *cost
		}
		b, _ := json.Marshal(body)
		req := httptest.NewRequest(http.MethodPost, "/internal/model-billing/record", bytes.NewReader(b))
		rr := httptest.NewRecorder()
		srv.recordInvocation(rr, req)
		if rr.Code != http.StatusOK && rr.Code != http.StatusCreated {
			t.Fatalf("record(%s) = %d: %s", purpose, rr.Code, rr.Body.String())
		}
		return reqID
	}

	voiceCost := 0.42
	sttID := record("voice_stt", &voiceCost)
	chatID := record("chat", nil)

	get := func(reqID uuid.UUID) (string, float64) {
		var lane string
		var cost float64
		if err := pool.QueryRow(context.Background(),
			`SELECT lane, total_cost_usd FROM usage_logs WHERE request_id=$1`, reqID).Scan(&lane, &cost); err != nil {
			t.Fatalf("read %s: %v", reqID, err)
		}
		return lane, cost
	}

	if lane, cost := get(sttID); lane != "assistant" || cost != voiceCost {
		t.Fatalf("voice_stt: lane=%q cost=%v, want assistant / %v (priced, not $0)", lane, cost, voiceCost)
	}
	if lane, _ := get(chatID); lane != "interactive" {
		t.Fatalf("chat: lane=%q, want interactive", lane)
	}

	// cold-review LOW-7 — an UNMAPPED purpose must default to 'interactive' (the safe default: an
	// unclassified spend is NOT silently hidden in the assistant lane).
	unmappedID := record("some_new_unmapped_purpose", nil)
	if lane, _ := get(unmappedID); lane != "interactive" {
		t.Fatalf("unmapped purpose: lane=%q, want interactive (COALESCE default)", lane)
	}

	// the lane reference + map are seeded by the migration
	var lanes int
	if err := pool.QueryRow(context.Background(), `SELECT count(*) FROM spend_lanes`).Scan(&lanes); err != nil {
		t.Fatal(err)
	}
	if lanes < 2 {
		t.Fatalf("spend_lanes must seed assistant+interactive, got %d", lanes)
	}
}
