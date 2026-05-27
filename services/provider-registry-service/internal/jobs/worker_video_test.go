package jobs

// worker_video_test.go — Phase 5d worker-level tests for video-gen dispatch.
//
// Coverage scope:
//   - videoJobOperations whitelist sanity
//   - classifyVideoError matrix (sentinels + ctx state + typed upstream)
//   - 5-place sync invariant (video_gen in handler validator + DB CHECK
//     + openapi enum)
//   - 3-way pairwise disjoint vs streamable + audio + image

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

// ── videoJobOperations whitelist ──────────────────────────────────────

func TestIsVideoJobOperation_Whitelist(t *testing.T) {
	if !isVideoJobOperation("video_gen") {
		t.Error("expected video_gen to be in videoJobOperations")
	}
}

func TestIsVideoJobOperation_RejectsNonVideo(t *testing.T) {
	cases := []string{
		"chat", "completion", "stt", "tts",
		"embedding", "translation",
		"image_gen", // image is its own dispatch path
		"entity_extraction",
		"", "unknown_operation",
	}
	for _, op := range cases {
		if isVideoJobOperation(op) {
			t.Errorf("expected %q to NOT be a video job operation", op)
		}
	}
}

// ── Disjoint-set invariant ───────────────────────────────────────────

// TestVideoJobOperations_Disjoint — Phase 5d 3-way pairwise check.
// Combined with Phase 5a's TestStreamableAudio_Disjoint (covers S∩A)
// and Phase 5c-α's TestImageJobOperations_Disjoint (covers I∩S, I∩A),
// the full 6-pair fan-out is verified across the three test functions.
// Pairwise disjoint implies 3-way disjoint (S∩A∩I∩V = ∅).
func TestVideoJobOperations_Disjoint(t *testing.T) {
	for op := range videoJobOperations {
		if _, dup := streamableOperations[op]; dup {
			t.Errorf("op %q in BOTH videoJobOperations AND streamableOperations — dispatch ambiguity", op)
		}
		if _, dup := audioJobOperations[op]; dup {
			t.Errorf("op %q in BOTH videoJobOperations AND audioJobOperations — dispatch ambiguity", op)
		}
		if _, dup := imageJobOperations[op]; dup {
			t.Errorf("op %q in BOTH videoJobOperations AND imageJobOperations — dispatch ambiguity", op)
		}
	}
	for op := range streamableOperations {
		if _, dup := videoJobOperations[op]; dup {
			t.Errorf("op %q in BOTH streamableOperations AND videoJobOperations — dispatch ambiguity", op)
		}
	}
	for op := range audioJobOperations {
		if _, dup := videoJobOperations[op]; dup {
			t.Errorf("op %q in BOTH audioJobOperations AND videoJobOperations — dispatch ambiguity", op)
		}
	}
	for op := range imageJobOperations {
		if _, dup := videoJobOperations[op]; dup {
			t.Errorf("op %q in BOTH imageJobOperations AND videoJobOperations — dispatch ambiguity", op)
		}
	}
}

// ── 5-place sync invariant ───────────────────────────────────────────

func TestVideoJobOperations_AlsoInValidJobOperations(t *testing.T) {
	// Phase 5d regression-lock — mirror of Phase 5a's audio test +
	// Phase 5c-α's image test. video_gen MUST appear in (a)
	// jobs_handler.go validJobOperations source, (b) migrate.go's
	// CHECK constraint, (c) openapi.yaml's JobOperation enum.
	rootPath := findRepoRoot(t)
	apiHandlerSrc := readFile(t, rootPath+"/services/provider-registry-service/internal/api/jobs_handler.go")
	migrateSrc := readFile(t, rootPath+"/services/provider-registry-service/internal/migrate/migrate.go")
	openapiSrc := readFile(t, rootPath+"/contracts/api/llm-gateway/v1/openapi.yaml")

	for op := range videoJobOperations {
		quoted := `"` + op + `"`
		yamlEntry := "        - " + op
		sqlQuoted := `'` + op + `'`
		if !strings.Contains(apiHandlerSrc, quoted) {
			t.Errorf("video op %q missing from jobs_handler.go validJobOperations — submit would fail with LLM_INVALID_REQUEST", op)
		}
		if !strings.Contains(migrateSrc, sqlQuoted) {
			t.Errorf("video op %q missing from migrate.go CHECK constraint — INSERT would fail (LLM_INTERNAL_ERROR)", op)
		}
		if !strings.Contains(openapiSrc, yamlEntry) {
			t.Errorf("video op %q missing from openapi.yaml JobOperation enum — contract drift", op)
		}
	}
}

// ── classifyVideoError matrix ────────────────────────────────────────

func TestClassifyVideoError_Cancelled(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	code, status := classifyVideoError(ctx, errors.New("any"))
	if code != "LLM_CANCELLED" || status != "cancelled" {
		t.Errorf("got (%s,%s), want (LLM_CANCELLED, cancelled)", code, status)
	}
}

func TestClassifyVideoError_DeadlineExceeded(t *testing.T) {
	ctx, cancel := context.WithDeadline(context.Background(), timeInPast())
	defer cancel()
	code, status := classifyVideoError(ctx, errors.New("any"))
	if code != "LLM_TIMEOUT" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_TIMEOUT, failed)", code, status)
	}
}

func TestClassifyVideoError_InvalidParams(t *testing.T) {
	code, status := classifyVideoError(context.Background(), provider.ErrVideoInvalidParams)
	if code != "LLM_INVALID_REQUEST" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_INVALID_REQUEST, failed)", code, status)
	}
}

func TestClassifyVideoError_InvalidParams_Wrapped(t *testing.T) {
	wrapped := wrapErr(provider.ErrVideoInvalidParams)
	code, _ := classifyVideoError(context.Background(), wrapped)
	if code != "LLM_INVALID_REQUEST" {
		t.Errorf("wrapped ErrVideoInvalidParams: got %s, want LLM_INVALID_REQUEST", code)
	}
}

func TestClassifyVideoError_ContentPolicy(t *testing.T) {
	code, status := classifyVideoError(context.Background(), provider.ErrVideoContentPolicy)
	if code != "LLM_VIDEO_CONTENT_POLICY_VIOLATION" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_VIDEO_CONTENT_POLICY_VIOLATION, failed)", code, status)
	}
}

func TestClassifyVideoError_GenerationFailed(t *testing.T) {
	code, status := classifyVideoError(context.Background(), provider.ErrVideoGenerationFailed)
	if code != "LLM_VIDEO_GENERATION_FAILED" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_VIDEO_GENERATION_FAILED, failed)", code, status)
	}
}

func TestClassifyVideoError_OperationNotSupported(t *testing.T) {
	code, status := classifyVideoError(context.Background(), provider.ErrOperationNotSupported)
	if code != "LLM_OPERATION_NOT_SUPPORTED" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_OPERATION_NOT_SUPPORTED, failed)", code, status)
	}
}

func TestClassifyVideoError_GenericMapsToUpstream(t *testing.T) {
	code, status := classifyVideoError(context.Background(), errors.New("upstream blew up"))
	if code != "LLM_UPSTREAM_ERROR" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_UPSTREAM_ERROR, failed)", code, status)
	}
}

func TestClassifyVideoError_RateLimitedTyped(t *testing.T) {
	rl := &provider.ErrUpstreamRateLimited{StatusCode: 429, Body: "slow"}
	code, status := classifyVideoError(context.Background(), rl)
	if code != "LLM_RATE_LIMITED" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_RATE_LIMITED, failed)", code, status)
	}
}

func TestClassifyVideoError_AuthFailedFrom401(t *testing.T) {
	perm := &provider.ErrUpstreamPermanent{StatusCode: 401, Body: "bad key"}
	code, status := classifyVideoError(context.Background(), perm)
	if code != "LLM_AUTH_FAILED" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_AUTH_FAILED, failed)", code, status)
	}
}

func TestClassifyVideoError_Permanent400IsUpstreamError(t *testing.T) {
	perm := &provider.ErrUpstreamPermanent{StatusCode: 400, Body: "bad input"}
	code, status := classifyVideoError(context.Background(), perm)
	if code != "LLM_UPSTREAM_ERROR" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_UPSTREAM_ERROR, failed)", code, status)
	}
}

func TestClassifyVideoError_Transient5xx(t *testing.T) {
	trans := &provider.ErrUpstreamTransient{StatusCode: 502, Body: "bad gateway"}
	code, status := classifyVideoError(context.Background(), trans)
	if code != "LLM_UPSTREAM_ERROR" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_UPSTREAM_ERROR, failed)", code, status)
	}
}
