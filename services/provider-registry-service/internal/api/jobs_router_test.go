package api

// Phase 2b — router-layer tests for the async LLM job endpoints.
// Mirrors the proxy_router_test.go pattern: validates auth + query
// param + json-body shape errors WITHOUT a real DB pool. The deeper
// path (insert + worker + cancel) is exercised by the live smoke
// test executed manually after rebuild.

import (
	"bytes"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"net/textproto"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func TestSubmitLlmJob_RequiresJWT(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/llm/jobs",
		strings.NewReader(`{}`),
	)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d body=%s", w.Code, w.Body.String())
	}
}

func TestInternalSubmitLlmJob_RequiresInternalToken(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/jobs?user_id="+uuid.NewString(),
		strings.NewReader(`{}`),
	)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("no internal token: expected 401, got %d", w.Code)
	}
}

func TestInternalSubmitLlmJob_MissingUserID(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/jobs",
		strings.NewReader(`{}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "user_id") {
		t.Errorf("expected user_id mention in body, got %s", w.Body.String())
	}
}

func TestInternalSubmitLlmJob_InvalidUserID(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/jobs?user_id=not-a-uuid",
		strings.NewReader(`{}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d", w.Code)
	}
}

func TestInternalSubmitLlmJob_NoJobsSubsystem(t *testing.T) {
	// router-only server has no DB pool → jobsRepo is nil → 503.
	// Phase 5a: caller-input validation runs BEFORE the 503 check, so a
	// fully-valid chat request is needed to exercise the 503 path
	// (anything else would return 400 first). This is intentional —
	// callers learn malformed-input issues immediately, even when the
	// subsystem happens to be down.
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/jobs?user_id="+uuid.NewString(),
		strings.NewReader(`{"operation":"chat","model_source":"user_model","model_ref":"`+uuid.NewString()+`","input":{"messages":[]}}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("expected 503 (no subsystem), got %d body=%s", w.Code, w.Body.String())
	}
}

// ── Phase 5a: tts rejection at submit ─────────────────────────────────

// TestInternalSubmitLlmJob_TtsRejectedAtSubmit pins the Phase 5a contract
// rule: tts is supported ONLY via /v1/llm/stream. Submitting tts via the
// jobs endpoint MUST return 400 with code LLM_OPERATION_NOT_SUPPORTED_VIA_JOBS
// and a hint pointing at the streaming endpoint, BEFORE the subsystem
// availability check (handler-level caller-input validation order).
func TestInternalSubmitLlmJob_TtsRejectedAtSubmit(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/jobs?user_id="+uuid.NewString(),
		strings.NewReader(`{
			"operation": "tts",
			"model_source": "user_model",
			"model_ref": "`+uuid.NewString()+`",
			"input": {"text": "hello", "voice": "alloy"}
		}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400 LLM_OPERATION_NOT_SUPPORTED_VIA_JOBS, got %d body=%s", w.Code, w.Body.String())
	}
	body := w.Body.String()
	if !strings.Contains(body, "LLM_OPERATION_NOT_SUPPORTED_VIA_JOBS") {
		t.Errorf("expected LLM_OPERATION_NOT_SUPPORTED_VIA_JOBS in body, got %s", body)
	}
	if !strings.Contains(body, "/v1/llm/stream") {
		t.Errorf("expected hint pointing at /v1/llm/stream, got %s", body)
	}
}

// TestInternalSubmitLlmJob_SttAcceptedAtSubmit confirms stt is NOT
// rejected at the handler — it routes to the worker (which then calls
// adapter.Transcribe). With a router-only server (no jobsRepo), a valid
// stt submission progresses past the validation gauntlet to the 503
// service-unavailable check. That's the signal the handler accepted it.
func TestInternalSubmitLlmJob_SttAcceptedAtSubmit(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/jobs?user_id="+uuid.NewString(),
		strings.NewReader(`{
			"operation": "stt",
			"model_source": "user_model",
			"model_ref": "`+uuid.NewString()+`",
			"input": {"audio_url": "https://example.com/audio.wav", "language": "en"}
		}`),
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	// stt is valid → progresses past validation → hits 503 (no DB pool in router-only mode).
	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("expected 503 (validation-passed, subsystem-not-ready), got %d body=%s", w.Code, w.Body.String())
	}
	if strings.Contains(w.Body.String(), "LLM_OPERATION_NOT_SUPPORTED_VIA_JOBS") {
		t.Errorf("stt MUST NOT be rejected at submit; body=%s", w.Body.String())
	}
}

func TestGetLlmJob_RequiresJWT(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodGet,
		"/v1/llm/jobs/"+uuid.NewString(),
		nil,
	)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestCancelLlmJob_RequiresJWT(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodDelete,
		"/v1/llm/jobs/"+uuid.NewString(),
		nil,
	)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", w.Code)
	}
}

func TestInternalGetLlmJob_InvalidJobID(t *testing.T) {
	// Even with valid auth + user_id, a malformed job_id path param
	// returns 400 LLM_INVALID_REQUEST. We expect 503 here because the
	// router-only server has no jobs subsystem; the validation 400
	// happens AFTER the subsystem check in our handler. This test
	// pins that ordering — change-detector for any future refactor
	// that flips the check order (which would silently mask invalid
	// IDs as 503).
	srv := newRouterOnlyServer(t)
	req := httptest.NewRequest(
		http.MethodGet,
		"/internal/llm/jobs/not-a-uuid?user_id="+uuid.NewString(),
		nil,
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("expected 503 (subsystem-check first), got %d", w.Code)
	}
}

// ── Phase 5b — multipart STT submit tests ─────────────────────────────

// buildSttMultipartRequest constructs a multipart/form-data POST request
// for /internal/llm/jobs. Caller supplies the audio bytes + optional
// extra form-fields. Returns the request ready to be served.
func buildSttMultipartRequest(t *testing.T, userID string, audioBytes []byte, audioFieldName, contentTypeOverride string, extra map[string]string) *http.Request {
	t.Helper()
	var buf bytes.Buffer
	mw := multipart.NewWriter(&buf)
	// Metadata fields.
	mustField := func(name, value string) {
		if err := mw.WriteField(name, value); err != nil {
			t.Fatalf("WriteField %s: %v", name, err)
		}
	}
	defaults := map[string]string{
		"operation":    "stt",
		"model_source": "user_model",
		"model_ref":    uuid.NewString(),
		"language":     "auto",
	}
	for k, v := range defaults {
		if _, override := extra[k]; !override {
			mustField(k, v)
		}
	}
	for k, v := range extra {
		mustField(k, v)
	}
	// File part — caller-controlled name (default "audio") + content-type.
	if audioBytes != nil {
		hdr := textproto.MIMEHeader{}
		hdr.Set("Content-Disposition", `form-data; name="`+audioFieldName+`"; filename="clip.webm"`)
		if contentTypeOverride != "" {
			hdr.Set("Content-Type", contentTypeOverride)
		} else {
			hdr.Set("Content-Type", "audio/webm")
		}
		fw, err := mw.CreatePart(hdr)
		if err != nil {
			t.Fatalf("CreatePart: %v", err)
		}
		if _, err := fw.Write(audioBytes); err != nil {
			t.Fatalf("write audio: %v", err)
		}
	}
	if err := mw.Close(); err != nil {
		t.Fatalf("multipart Close: %v", err)
	}
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/jobs?user_id="+userID,
		&buf,
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", mw.FormDataContentType())
	return req
}

// TestInternalSubmitLlmJob_MultipartStt_ValidationPasses confirms a
// well-formed multipart STT submission is accepted past handler-level
// validation. Router-only server has no DB, so a fully-valid request
// progresses past validation to the 503 service-unavailable check —
// same pattern as TestInternalSubmitLlmJob_SttAcceptedAtSubmit.
//
// Cases this guards against: handler typos in field-name extraction,
// regression to JSON-only Content-Type dispatch, accidental rejection
// of the multipart variant.
func TestInternalSubmitLlmJob_MultipartStt_ValidationPasses(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := buildSttMultipartRequest(t, uuid.NewString(),
		[]byte("WEBMfake"), "audio", "", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("expected 503 (validation-passed, no subsystem), got %d body=%s", w.Code, w.Body.String())
	}
	// Anti-regression — must NOT be classified as a JSON-mode error.
	if strings.Contains(w.Body.String(), "invalid JSON") {
		t.Errorf("multipart request was misrouted to JSON path; body=%s", w.Body.String())
	}
}

// TestInternalSubmitLlmJob_MultipartCaseInsensitiveContentType pins
// Fix #4 — RFC 2045 case-insensitivity. `Content-Type: MULTIPART/FORM-DATA`
// MUST dispatch to the multipart handler, not the JSON one (which would
// fail with "invalid JSON body").
func TestInternalSubmitLlmJob_MultipartCaseInsensitiveContentType(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := buildSttMultipartRequest(t, uuid.NewString(),
		[]byte("WEBMfake"), "audio", "", nil)
	// Uppercase ONLY the media-type portion (not the boundary= param) —
	// per RFC 2045 §5.1 the type/subtype is case-insensitive but the
	// boundary parameter value is case-sensitive. Naive strings.HasPrefix
	// against "multipart/form-data" (lowercase) would miss this.
	ct := req.Header.Get("Content-Type")
	idx := strings.Index(ct, ";")
	if idx < 0 {
		t.Fatalf("expected boundary param in Content-Type %q", ct)
	}
	req.Header.Set("Content-Type", strings.ToUpper(ct[:idx])+ct[idx:])
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("expected 503 (validation-passed), got %d body=%s", w.Code, w.Body.String())
	}
	if strings.Contains(w.Body.String(), "invalid JSON") {
		t.Errorf("uppercase Content-Type misrouted to JSON path; body=%s", w.Body.String())
	}
}

// TestInternalSubmitLlmJob_MultipartOversizeReturns413 pins Fix #1 —
// http.MaxBytesReader catches a >25MB body, ParseMultipartForm returns
// *http.MaxBytesError, handler maps to 413 LLM_AUDIO_TOO_LARGE.
//
// We exceed by SttMultipartOverhead+1KB to guarantee tripping the cap
// even after the multipart envelope overhead allowance.
func TestInternalSubmitLlmJob_MultipartOversizeReturns413(t *testing.T) {
	srv := newRouterOnlyServer(t)
	oversized := make([]byte, SttMaxAudioBytes+sttMultipartOverhead+1024)
	for i := range oversized {
		oversized[i] = 'A'
	}
	req := buildSttMultipartRequest(t, uuid.NewString(),
		oversized, "audio", "", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusRequestEntityTooLarge {
		t.Errorf("expected 413, got %d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "LLM_AUDIO_TOO_LARGE") {
		t.Errorf("expected LLM_AUDIO_TOO_LARGE in body, got %s", w.Body.String())
	}
}

// TestInternalSubmitLlmJob_MultipartWrongOperation pins design §2.1 —
// only operation=stt is supported on multipart. Other operations return
// 400 with a hint to use JSON.
func TestInternalSubmitLlmJob_MultipartWrongOperation(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := buildSttMultipartRequest(t, uuid.NewString(),
		[]byte("nope"), "audio", "", map[string]string{
			"operation": "chat",
		})
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "not supported via multipart") {
		t.Errorf("expected 'not supported via multipart' hint, got %s", w.Body.String())
	}
}

// TestInternalSubmitLlmJob_MultipartChunkingFieldRejected pins Fix #12 —
// callers may NOT send a `chunking` form-field on stt multipart submits.
// STT runs as a single upstream call regardless of audio length.
func TestInternalSubmitLlmJob_MultipartChunkingFieldRejected(t *testing.T) {
	srv := newRouterOnlyServer(t)
	req := buildSttMultipartRequest(t, uuid.NewString(),
		[]byte("nope"), "audio", "", map[string]string{
			"chunking": `{"size":15,"strategy":"paragraphs"}`,
		})
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "chunking not accepted") {
		t.Errorf("expected 'chunking not accepted' hint, got %s", w.Body.String())
	}
}

// TestInternalSubmitLlmJob_MultipartZeroByteAudioReturns400 pins
// /review-impl(QC) MED#1 — empty multipart file field (0 bytes) must
// reject at the handler with LLM_INVALID_REQUEST, NOT pass through to
// the adapter where it'd produce a confusing LLM_UPSTREAM_ERROR after
// OpenAI rejects the empty multipart file.
func TestInternalSubmitLlmJob_MultipartZeroByteAudioReturns400(t *testing.T) {
	srv := newRouterOnlyServer(t)
	// audioBytes=[]byte{} (empty non-nil slice) — buildSttMultipartRequest
	// still writes the file part header but with no content.
	req := buildSttMultipartRequest(t, uuid.NewString(),
		[]byte{}, "audio", "", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "empty") {
		t.Errorf("expected 'empty' in body, got %s", w.Body.String())
	}
}

// TestInternalSubmitLlmJob_MultipartEmptyContentTypeReturns400 pins
// /review-impl(QC) MED#2 — caller MUST set Content-Type on the audio
// file part. The handler refuses to fall back to a default so
// misformatted audio doesn't get misdecoded by Whisper.
func TestInternalSubmitLlmJob_MultipartEmptyContentTypeReturns400(t *testing.T) {
	srv := newRouterOnlyServer(t)
	// Build a request, then strip the file part's Content-Type by
	// constructing it manually with no header.
	var buf bytes.Buffer
	mw := multipart.NewWriter(&buf)
	for k, v := range map[string]string{
		"operation":    "stt",
		"model_source": "user_model",
		"model_ref":    uuid.NewString(),
		"language":     "auto",
	} {
		_ = mw.WriteField(k, v)
	}
	hdr := textproto.MIMEHeader{}
	hdr.Set("Content-Disposition", `form-data; name="audio"; filename="clip.webm"`)
	// Deliberately NO Content-Type header on this part.
	fw, _ := mw.CreatePart(hdr)
	_, _ = fw.Write([]byte("WEBMbytes"))
	_ = mw.Close()

	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/llm/jobs?user_id="+uuid.NewString(),
		&buf,
	)
	req.Header.Set("X-Internal-Token", routerTestInternalToken)
	req.Header.Set("Content-Type", mw.FormDataContentType())
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d body=%s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "Content-Type") {
		t.Errorf("expected 'Content-Type' hint in body, got %s", w.Body.String())
	}
}

// TestInternalSubmitLlmJob_MultipartWrongFileFieldName pins Fix #13 —
// uploading the audio under a field name other than "audio" returns
// 400 with an explicit list of received field names, so the caller's
// typo surfaces immediately rather than a generic parse failure.
func TestInternalSubmitLlmJob_MultipartWrongFileFieldName(t *testing.T) {
	srv := newRouterOnlyServer(t)
	// "file" mimics the OpenAI Whisper native field name — common
	// caller mistake.
	req := buildSttMultipartRequest(t, uuid.NewString(),
		[]byte("nope"), "file", "", nil)
	w := httptest.NewRecorder()
	srv.Router().ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400, got %d body=%s", w.Code, w.Body.String())
	}
	body := w.Body.String()
	if !strings.Contains(body, "expected file field 'audio'") {
		t.Errorf("expected field-name hint, got %s", body)
	}
	if !strings.Contains(body, "file") {
		t.Errorf("expected received-field-list ('file') in body, got %s", body)
	}
}
