package consumer

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/notification-service/internal/category"
)

// P2·C — the dedup key is the at-least-once idempotency key. A redelivery of the
// same terminal event must derive the SAME key (job_id:status) so ON CONFLICT
// collapses it; a drift in this shape would silently reopen the duplicate-row hole.
func TestTransform_DedupKeyIsJobIDStatus(t *testing.T) {
	jid := uuid.New()
	args := transformTerminalEvent(terminalEvent{
		JobID: jid, OwnerUserID: uuid.New(), Operation: "chat", Status: "completed",
	})
	if want := jid.String() + ":completed"; args.DedupKey != want {
		t.Errorf("dedup_key: got %q want %q", args.DedupKey, want)
	}
	// Distinct terminal statuses of one job stay distinct (a completed then a late
	// cancelled are different notifications, not dupes).
	failed := transformTerminalEvent(terminalEvent{JobID: jid, OwnerUserID: uuid.New(), Status: "failed"})
	if failed.DedupKey == args.DedupKey {
		t.Errorf("distinct statuses must not share a dedup key: %q", failed.DedupKey)
	}
	// Empty status → no trailing colon (well-formed key).
	empty := transformTerminalEvent(terminalEvent{JobID: jid, OwnerUserID: uuid.New()})
	if empty.DedupKey != jid.String() {
		t.Errorf("empty-status key: got %q want %q", empty.DedupKey, jid.String())
	}
}

// P2·C — an upstream error message that echoed a credential must be scrubbed
// before it becomes a notification body (which is stored + pushed to the user).
func TestTransform_RedactsSecretInErrorBody(t *testing.T) {
	args := transformTerminalEvent(terminalEvent{
		JobID: uuid.New(), OwnerUserID: uuid.New(), Operation: "chat", Status: "failed",
		ErrorCode: "UPSTREAM_401", ErrorMessage: "provider rejected: Bearer sk-proj-DEADbeef0123456789",
	})
	if strings.Contains(args.Body, "sk-proj-DEADbeef0123456789") || strings.Contains(args.Body, "Bearer sk-") {
		t.Errorf("secret survived into notification body: %q", args.Body)
	}
	if !strings.Contains(args.Body, "UPSTREAM_401") {
		t.Errorf("legit error code should survive redaction: %q", args.Body)
	}
}

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

// TestNotificationIsContentFreeByConstruction locks the D16/spec-11-Q6 invariant a
// Phase-3 diary-distill notification depends on: a notification body/title is derived
// ONLY from job metadata (operation label, status, error code/message), NEVER from any
// payload content — because TerminalEvent carries no title/summary/content field at all.
// A completed diary-distill notification is therefore content-free (empty body) by
// construction: "Journal entry completed", not "You journaled about the layoff with Sarah".
//
// The ONE residual leak vector for Phase 3 is a FAILED distill job whose ErrorMessage
// echoes diary text (bodyFor surfaces error_message on failure). That is a Phase-3
// producer-side constraint recorded in the plan: a diary/journal operation must emit a
// generic error_code with NO message, or be registered in a body-suppression set. This
// test is the tripwire — it will red if a content field is ever read into title/body.
func TestNotificationIsContentFreeByConstruction(t *testing.T) {
	// A hypothetical diary-distill terminal event. Even if a producer stuffed a
	// content-looking operation, the SUCCESS body is empty and the title is only the
	// op label — no entry content can appear.
	secret := "the layoff conversation with Sarah on Tuesday"
	for _, status := range []string{"completed", "cancelled"} {
		args := transformTerminalEvent(terminalEvent{
			JobID: uuid.New(), OwnerUserID: uuid.New(),
			Operation: "journal_distill", Status: status,
			// These fields are metadata, not content — but assert nothing content-like
			// leaks even if a future producer misused them.
			FinishReason: secret, ErrorCode: secret,
		})
		if args.Body != "" {
			t.Errorf("status=%s: a diary-distill body must be content-free (empty), got %q", status, args.Body)
		}
		if strings.Contains(args.Title, "Sarah") || strings.Contains(args.Title, "layoff") {
			t.Errorf("status=%s: title leaked content: %q", status, args.Title)
		}
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
		"video_gen":           "Video gen", // Phase 5d
		"audio_gen":           "Audio gen", // Phase 5e-β.2
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

// TestTransform_CategoryPassesSharedValidation proves the consumer's insert
// path shares the HTTP path's single source-of-truth enum: the category it
// produces must be accepted by category.Valid — the same guard now gating
// the consumer's insert (audit P0-4 / NOTIF-2). If someone changes the
// consumer's category to a value not in the shared set, its inserts would be
// dropped as poison; this test catches that drift.
func TestTransform_CategoryPassesSharedValidation(t *testing.T) {
	args := transformTerminalEvent(terminalEvent{
		JobID:       uuid.New(),
		OwnerUserID: uuid.New(),
		Operation:   "chat",
		Status:      "completed",
	})
	if !category.Valid(args.Category) {
		t.Fatalf("consumer category %q is not in the shared enum — its inserts would be dropped", args.Category)
	}
}

func TestOpLabel_EmptyFallback(t *testing.T) {
	if got := opLabel(""); got != "Job" {
		t.Errorf("empty op should default to Job, got %q", got)
	}
}

// TestTransform_I18nKeyAndParams_AlongsideFallback proves D-NOTIF-I18N
// (NOTIF-1): a terminal event yields BOTH the rendered English title/body
// fallback AND a stable message_key + interpolation params. A locale-aware FE
// renders from the key; every other client keeps showing title/body.
func TestTransform_I18nKeyAndParams_AlongsideFallback(t *testing.T) {
	args := transformTerminalEvent(terminalEvent{
		JobID:       uuid.New(),
		OwnerUserID: uuid.New(),
		Operation:   "entity_extraction",
		Status:      "completed",
	})

	// Rendered English fallback is still written as before.
	if args.Title != "Entity extraction completed" {
		t.Errorf("fallback title wrong: %q", args.Title)
	}

	// Stable i18n key: notif.<category>.<status>.
	if args.MessageKey != "notif.llm_job.completed" {
		t.Errorf("message_key wrong: %q, want notif.llm_job.completed", args.MessageKey)
	}

	// Params carry the interpolation values (operation here).
	var params map[string]any
	if err := json.Unmarshal(args.MessageParams, &params); err != nil {
		t.Fatalf("message_params not JSON: %v (%s)", err, args.MessageParams)
	}
	if params["operation"] != "entity_extraction" {
		t.Errorf("message_params.operation wrong: %v", params["operation"])
	}
	if _, present := params["error_code"]; present {
		t.Errorf("completed event should not carry error_code, got %v", params)
	}
}

// TestTransform_I18nFailedCarriesErrorCode proves a failure's message_params
// carry the error_code (so a localized error notification can name the
// failure), and the key reflects the failed status.
func TestTransform_I18nFailedCarriesErrorCode(t *testing.T) {
	args := transformTerminalEvent(terminalEvent{
		JobID:        uuid.New(),
		OwnerUserID:  uuid.New(),
		Operation:    "translation",
		Status:       "failed",
		ErrorCode:    "LLM_UPSTREAM_ERROR",
		ErrorMessage: "provider returned 502",
	})
	if args.MessageKey != "notif.llm_job.failed" {
		t.Errorf("message_key wrong: %q, want notif.llm_job.failed", args.MessageKey)
	}
	var params map[string]any
	if err := json.Unmarshal(args.MessageParams, &params); err != nil {
		t.Fatalf("message_params not JSON: %v", err)
	}
	if params["operation"] != "translation" {
		t.Errorf("message_params.operation wrong: %v", params["operation"])
	}
	if params["error_code"] != "LLM_UPSTREAM_ERROR" {
		t.Errorf("message_params.error_code wrong: %v", params["error_code"])
	}
	// Fallback body still rendered.
	if !strings.Contains(args.Body, "provider returned 502") {
		t.Errorf("fallback body missing error message: %q", args.Body)
	}
}
