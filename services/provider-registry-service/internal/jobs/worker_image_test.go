package jobs

// worker_image_test.go — Phase 5c-α worker-level tests for the
// image-gen dispatch path.
//
// Coverage scope:
//   - imageJobOperations whitelist sanity
//   - classifyImageError matrix (sentinel sentinels + ctx state +
//     typed upstream errors)
//   - 5-place sync invariant (image_gen in handler validator + DB CHECK
//     + openapi enum — SDK Literal covered separately by Python tests)
//   - Disjoint-set invariant (image ∩ streamable = ∅; image ∩ audio = ∅)

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

// ── imageJobOperations whitelist ───────────────────────────────────────

func TestIsImageJobOperation_Whitelist(t *testing.T) {
	if !isImageJobOperation("image_gen") {
		t.Error("expected image_gen to be in imageJobOperations")
	}
}

func TestIsImageJobOperation_RejectsNonImage(t *testing.T) {
	cases := []string{
		"chat",
		"completion",
		"stt",
		"tts",
		"embedding",
		"translation",
		"entity_extraction",
		"",
		"unknown_operation",
	}
	for _, op := range cases {
		if isImageJobOperation(op) {
			t.Errorf("expected %q to NOT be an image job operation", op)
		}
	}
}

// ── Disjoint-set invariant (Fix #2) ────────────────────────────────────

// TestImageJobOperations_Disjoint pins Phase 5c-α /review-impl(DESIGN)
// MED#2 — the worker has three dispatch maps (streamable, audio, image)
// and routes by first-match in worker.go::Process. A future regression
// where someone adds an op to two maps would silently change dispatch
// path. This test asserts the maps are disjoint by construction.
func TestImageJobOperations_Disjoint(t *testing.T) {
	for op := range imageJobOperations {
		if _, dup := streamableOperations[op]; dup {
			t.Errorf("op %q in BOTH imageJobOperations AND streamableOperations — "+
				"dispatch ambiguity; pick one", op)
		}
		if _, dup := audioJobOperations[op]; dup {
			t.Errorf("op %q in BOTH imageJobOperations AND audioJobOperations — "+
				"dispatch ambiguity; pick one", op)
		}
	}
	for op := range streamableOperations {
		if _, dup := imageJobOperations[op]; dup {
			t.Errorf("op %q in BOTH streamableOperations AND imageJobOperations — "+
				"dispatch ambiguity; pick one", op)
		}
	}
	for op := range audioJobOperations {
		if _, dup := imageJobOperations[op]; dup {
			t.Errorf("op %q in BOTH audioJobOperations AND imageJobOperations — "+
				"dispatch ambiguity; pick one", op)
		}
	}
}

// ── 5-place sync invariant ─────────────────────────────────────────────

func TestImageJobOperations_AlsoInValidJobOperations(t *testing.T) {
	// Phase 5c-α regression-lock (mirrors Phase 5a's
	// TestAudioJobOperations_AlsoInValidJobOperations): every image-gen
	// op MUST appear in (a) jobs_handler.go validJobOperations source,
	// (b) migrate.go's CHECK constraint, (c) openapi.yaml's JobOperation
	// enum. Source-grep approach pins the 4 non-SDK slots of the 5-place
	// invariant. SDK Literal is covered by Python import-time validation.
	//
	// Per design §2.1, all 4 slots are already populated for image_gen
	// (from Phase 2b enum reservation) — this test pins they STAY
	// populated, not that 5c-α adds them.
	rootPath := findRepoRoot(t)
	apiHandlerSrc := readFile(t, rootPath+"/services/provider-registry-service/internal/api/jobs_handler.go")
	migrateSrc := readFile(t, rootPath+"/services/provider-registry-service/internal/migrate/migrate.go")
	openapiSrc := readFile(t, rootPath+"/contracts/api/llm-gateway/v1/openapi.yaml")

	for op := range imageJobOperations {
		quoted := `"` + op + `"`
		yamlEntry := "        - " + op
		sqlQuoted := `'` + op + `'`
		if !strings.Contains(apiHandlerSrc, quoted) {
			t.Errorf("image op %q missing from jobs_handler.go validJobOperations — "+
				"submit would fail with LLM_INVALID_REQUEST", op)
		}
		if !strings.Contains(migrateSrc, sqlQuoted) {
			t.Errorf("image op %q missing from migrate.go CHECK constraint — "+
				"INSERT would fail with constraint violation (LLM_INTERNAL_ERROR)", op)
		}
		if !strings.Contains(openapiSrc, yamlEntry) {
			t.Errorf("image op %q missing from openapi.yaml JobOperation enum — "+
				"contract drift; SDK clients won't accept this op", op)
		}
	}
}

// ── D-PHASE5E — provider identity in the result map ────────────────────

// TestImageResultCarriesProviderIdentity pins that runImageGenJob's result
// map surfaces provider_kind + provider_model_name (D-PHASE5E). The worker
// tests have no full-job harness (all pure-helper), so this is a source-level
// lock — matching the file's 5-place-sync grep-lock convention. It catches the
// real regression: a refactor dropping either key from the result map, which
// would silently re-blank book-service's ai_model + billing analytics.
func TestImageResultCarriesProviderIdentity(t *testing.T) {
	rootPath := findRepoRoot(t)
	src := readFile(t, rootPath+"/services/provider-registry-service/internal/jobs/worker_image.go")
	for _, key := range []string{`"provider_kind":`, `"provider_model_name":`} {
		if !strings.Contains(src, key) {
			t.Errorf("worker_image.go result map missing %s — book-service ai_model + "+
				"billing provider_kind would re-blank (D-PHASE5E regression)", key)
		}
	}
	// And the values must come from the resolved vars, not a hardcoded "".
	// (Alignment-independent: match the key→var pairing tolerant of gofmt's
	// map-literal spacing, which shifts if a longer key is ever added.)
	for _, pair := range []struct{ key, val string }{
		{`"provider_kind":`, "providerKind"},
		{`"provider_model_name":`, "providerModelName"},
	} {
		idx := strings.Index(src, pair.key)
		if idx < 0 {
			continue // key-presence already asserted above
		}
		rest := src[idx+len(pair.key):]
		nl := strings.IndexByte(rest, '\n')
		if nl < 0 {
			nl = len(rest)
		}
		if !strings.Contains(rest[:nl], pair.val) {
			t.Errorf("worker_image.go must populate %s from the resolved %s var, not a literal",
				pair.key, pair.val)
		}
	}
}

// ── classifyImageError matrix ──────────────────────────────────────────

func TestClassifyImageError_Cancelled(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	code, status := classifyImageError(ctx, errors.New("any error"))
	if code != "LLM_CANCELLED" || status != "cancelled" {
		t.Errorf("got (%s,%s), want (LLM_CANCELLED, cancelled)", code, status)
	}
}

func TestClassifyImageError_DeadlineExceeded(t *testing.T) {
	ctx, cancel := context.WithDeadline(context.Background(), timeInPast())
	defer cancel()
	code, status := classifyImageError(ctx, errors.New("any error"))
	if code != "LLM_TIMEOUT" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_TIMEOUT, failed)", code, status)
	}
}

func TestClassifyImageError_InvalidParams(t *testing.T) {
	// Phase 5c-α /review-impl(DESIGN) MED#5 — ErrImageInvalidParams maps
	// to LLM_INVALID_REQUEST (caller bug, not retryable transient).
	code, status := classifyImageError(context.Background(), provider.ErrImageInvalidParams)
	if code != "LLM_INVALID_REQUEST" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_INVALID_REQUEST, failed)", code, status)
	}
}

func TestClassifyImageError_InvalidParams_Wrapped(t *testing.T) {
	wrapped := wrapErr(provider.ErrImageInvalidParams)
	code, _ := classifyImageError(context.Background(), wrapped)
	if code != "LLM_INVALID_REQUEST" {
		t.Errorf("wrapped ErrImageInvalidParams: got %s, want LLM_INVALID_REQUEST", code)
	}
}

func TestClassifyImageError_ContentPolicy(t *testing.T) {
	code, status := classifyImageError(context.Background(), provider.ErrImageContentPolicy)
	if code != "LLM_IMAGE_CONTENT_POLICY_VIOLATION" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_IMAGE_CONTENT_POLICY_VIOLATION, failed)", code, status)
	}
}

func TestClassifyImageError_GenerationFailed(t *testing.T) {
	code, status := classifyImageError(context.Background(), provider.ErrImageGenerationFailed)
	if code != "LLM_IMAGE_GENERATION_FAILED" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_IMAGE_GENERATION_FAILED, failed)", code, status)
	}
}

func TestClassifyImageError_OperationNotSupported(t *testing.T) {
	code, status := classifyImageError(context.Background(), provider.ErrOperationNotSupported)
	if code != "LLM_OPERATION_NOT_SUPPORTED" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_OPERATION_NOT_SUPPORTED, failed)", code, status)
	}
}

func TestClassifyImageError_GenericMapsToUpstream(t *testing.T) {
	code, status := classifyImageError(context.Background(), errors.New("upstream blew up: 502"))
	if code != "LLM_UPSTREAM_ERROR" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_UPSTREAM_ERROR, failed)", code, status)
	}
}

func TestClassifyImageError_RateLimitedTyped(t *testing.T) {
	rl := &provider.ErrUpstreamRateLimited{StatusCode: 429, Body: "slow down"}
	code, status := classifyImageError(context.Background(), rl)
	if code != "LLM_RATE_LIMITED" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_RATE_LIMITED, failed)", code, status)
	}
}

func TestClassifyImageError_AuthFailedFrom401(t *testing.T) {
	perm := &provider.ErrUpstreamPermanent{StatusCode: 401, Body: "bad key"}
	code, status := classifyImageError(context.Background(), perm)
	if code != "LLM_AUTH_FAILED" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_AUTH_FAILED, failed)", code, status)
	}
}

func TestClassifyImageError_AuthFailedFrom403(t *testing.T) {
	perm := &provider.ErrUpstreamPermanent{StatusCode: 403, Body: "forbidden"}
	code, status := classifyImageError(context.Background(), perm)
	if code != "LLM_AUTH_FAILED" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_AUTH_FAILED, failed)", code, status)
	}
}

func TestClassifyImageError_Permanent400IsUpstreamError(t *testing.T) {
	perm := &provider.ErrUpstreamPermanent{StatusCode: 400, Body: "bad input"}
	code, status := classifyImageError(context.Background(), perm)
	if code != "LLM_UPSTREAM_ERROR" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_UPSTREAM_ERROR, failed)", code, status)
	}
}

func TestClassifyImageError_Transient5xx(t *testing.T) {
	trans := &provider.ErrUpstreamTransient{StatusCode: 502, Body: "bad gateway"}
	code, status := classifyImageError(context.Background(), trans)
	if code != "LLM_UPSTREAM_ERROR" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_UPSTREAM_ERROR, failed)", code, status)
	}
}
