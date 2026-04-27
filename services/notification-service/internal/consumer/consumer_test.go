package consumer

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func TestTransform_CompletedHasNoBody(t *testing.T) {
	uid := uuid.New()
	jid := uuid.New()
	args := transformTerminalEvent(terminalEvent{
		JobID:        jid,
		OwnerUserID:  uid,
		Operation:    "chat",
		Status:       "completed",
		FinishReason: "stop",
	})
	if args.UserID != uid {
		t.Errorf("user_id pass-through wrong: got %s want %s", args.UserID, uid)
	}
	if args.Category != "llm_job" {
		t.Errorf("category wrong: %q", args.Category)
	}
	if args.Title != "Chat completed" {
		t.Errorf("title wrong: %q", args.Title)
	}
	if args.Body != "" {
		t.Errorf("body should be empty for success, got %q", args.Body)
	}
	var meta map[string]any
	if err := json.Unmarshal(args.Metadata, &meta); err != nil {
		t.Fatalf("metadata not JSON: %v", err)
	}
	if meta["job_id"] != jid.String() {
		t.Errorf("metadata job_id wrong: %v", meta["job_id"])
	}
	if meta["finish_reason"] != "stop" {
		t.Errorf("finish_reason missing in metadata: %v", meta)
	}
}

func TestTransform_FailedIncludesErrorCodeAndMessage(t *testing.T) {
	args := transformTerminalEvent(terminalEvent{
		JobID:        uuid.New(),
		OwnerUserID:  uuid.New(),
		Operation:    "entity_extraction",
		Status:       "failed",
		ErrorCode:    "LLM_UPSTREAM_ERROR",
		ErrorMessage: "provider returned 502",
	})
	if args.Title != "Entity extraction failed" {
		t.Errorf("title wrong: %q", args.Title)
	}
	if !strings.Contains(args.Body, "LLM_UPSTREAM_ERROR") {
		t.Errorf("body missing error code: %q", args.Body)
	}
	if !strings.Contains(args.Body, "provider returned 502") {
		t.Errorf("body missing error message: %q", args.Body)
	}
}

func TestTransform_FailedTruncatesLongMessage(t *testing.T) {
	long := strings.Repeat("x", 1000)
	args := transformTerminalEvent(terminalEvent{
		JobID:        uuid.New(),
		OwnerUserID:  uuid.New(),
		Operation:    "translation",
		Status:       "failed",
		ErrorMessage: long,
	})
	if len(args.Body) > 250 {
		t.Errorf("body length %d exceeded cap; should be ~240+'...'", len(args.Body))
	}
	if !strings.HasSuffix(args.Body, "...") {
		t.Errorf("expected truncation suffix, got %q", args.Body[len(args.Body)-10:])
	}
}

func TestTransform_CancelledTitle(t *testing.T) {
	args := transformTerminalEvent(terminalEvent{
		JobID:       uuid.New(),
		OwnerUserID: uuid.New(),
		Operation:   "chat",
		Status:      "cancelled",
	})
	if args.Title != "Chat cancelled" {
		t.Errorf("title wrong: %q", args.Title)
	}
	if args.Body != "" {
		t.Errorf("cancelled should have empty body: %q", args.Body)
	}
}

func TestOpLabel_AllJobOperations(t *testing.T) {
	cases := map[string]string{
		"chat":                "Chat",
		"completion":          "Completion",
		"embedding":           "Embedding",
		"stt":                 "Stt",
		"tts":                 "Tts",
		"image_gen":           "Image gen",
		"entity_extraction":   "Entity extraction",
		"relation_extraction": "Relation extraction",
		"event_extraction":    "Event extraction",
		"translation":         "Translation",
	}
	for op, want := range cases {
		got := opLabel(op)
		if got != want {
			t.Errorf("opLabel(%q) = %q, want %q", op, got, want)
		}
	}
}

func TestOpLabel_EmptyFallback(t *testing.T) {
	if got := opLabel(""); got != "Job" {
		t.Errorf("empty op should default to Job, got %q", got)
	}
}
