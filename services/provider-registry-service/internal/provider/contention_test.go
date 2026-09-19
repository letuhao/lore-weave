package provider

import "testing"

// #286 / plan 2026-09-19 T13 — LM Studio's answer when two loads collide, verbatim from run 4's
// llm_jobs (2026-09-18 19:04:26 UTC), must be retryable contention; any other 4xx stays permanent.
const loadAbortBody = `{
    "error": {
        "message": "Failed to load model \"google/gemma-4-12b-qat\". Error: Engine protocol startup was aborted.",
        "type": "invalid_request_error",
        "param": "model",
        "code": null
    }
}`

func TestLoadAbort_IsContention_RetryableButNotAHealthFailure(t *testing.T) {
	err := ClassifyUpstreamHTTP(400, loadAbortBody, nil)
	if ErrorClass(err) != "contention" {
		t.Fatalf("the load-abort 400 must classify as contention, got %s (%v)", ErrorClass(err), err)
	}
	if !IsRetryableUpstreamError(err) {
		t.Fatal("contention must be retried: the same call succeeds once the other model has loaded")
	}
	if IsTransientUpstreamError(err) {
		t.Fatal("contention must NOT be a health failure: the breaker counts IsTransientUpstreamError")
	}
}

func TestOtherModelLoadFailures_StayPermanent(t *testing.T) {
	for _, body := range []string{
		`{"error":{"message":"Failed to load model \"no-such-model\". Error: model not found"}}`,
		`{"error":{"message":"invalid request: messages required"}}`,
	} {
		err := ClassifyUpstreamHTTP(400, body, nil)
		if ErrorClass(err) != "permanent" || IsRetryableUpstreamError(err) {
			t.Fatalf("a real bad request must stay permanent and unretried: %s → %s", body, ErrorClass(err))
		}
	}
}
