package jobs

// worker_vision_test.go — PDF-import vision op (docs/specs/2026-07-06-pdf-book-import.md
// L5) worker-level tests for vision-caption dispatch. Mirrors
// worker_video_test.go's coverage shape.
//
// Coverage scope:
//   - visionJobOperations whitelist sanity
//   - classifyVisionError matrix (sentinels + ctx state + typed upstream)
//   - 5-place sync invariant (vision in handler validator + DB CHECK + openapi enum)
//   - 4-way pairwise disjoint vs streamable + audio + image + video

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/loreweave/provider-registry-service/internal/provider"
)

// ── visionJobOperations whitelist ──────────────────────────────────────

func TestIsVisionJobOperation_Whitelist(t *testing.T) {
	if !isVisionJobOperation("vision") {
		t.Error("expected vision to be in visionJobOperations")
	}
}

func TestIsVisionJobOperation_RejectsNonVision(t *testing.T) {
	cases := []string{
		"chat", "completion", "stt", "tts",
		"embedding", "translation",
		"image_gen", "video_gen", "audio_gen",
		"entity_extraction",
		"", "unknown_operation",
	}
	for _, op := range cases {
		if isVisionJobOperation(op) {
			t.Errorf("expected %q to NOT be a vision job operation", op)
		}
	}
}

// ── Disjoint-set invariant ───────────────────────────────────────────

func TestVisionJobOperations_Disjoint(t *testing.T) {
	for op := range visionJobOperations {
		if _, dup := streamableOperations[op]; dup {
			t.Errorf("op %q in BOTH visionJobOperations AND streamableOperations — dispatch ambiguity", op)
		}
		if _, dup := audioJobOperations[op]; dup {
			t.Errorf("op %q in BOTH visionJobOperations AND audioJobOperations — dispatch ambiguity", op)
		}
		if _, dup := imageJobOperations[op]; dup {
			t.Errorf("op %q in BOTH visionJobOperations AND imageJobOperations — dispatch ambiguity", op)
		}
		if _, dup := videoJobOperations[op]; dup {
			t.Errorf("op %q in BOTH visionJobOperations AND videoJobOperations — dispatch ambiguity", op)
		}
	}
	for op := range streamableOperations {
		if _, dup := visionJobOperations[op]; dup {
			t.Errorf("op %q in BOTH streamableOperations AND visionJobOperations — dispatch ambiguity", op)
		}
	}
	for op := range audioJobOperations {
		if _, dup := visionJobOperations[op]; dup {
			t.Errorf("op %q in BOTH audioJobOperations AND visionJobOperations — dispatch ambiguity", op)
		}
	}
	for op := range imageJobOperations {
		if _, dup := visionJobOperations[op]; dup {
			t.Errorf("op %q in BOTH imageJobOperations AND visionJobOperations — dispatch ambiguity", op)
		}
	}
	for op := range videoJobOperations {
		if _, dup := visionJobOperations[op]; dup {
			t.Errorf("op %q in BOTH videoJobOperations AND visionJobOperations — dispatch ambiguity", op)
		}
	}
}

// ── 5-place sync invariant ───────────────────────────────────────────

func TestVisionJobOperations_AlsoInValidJobOperations(t *testing.T) {
	// Mirror of Phase 5d's video test. vision MUST appear in (a)
	// jobs_handler.go validJobOperations source, (b) migrate.go's CHECK
	// constraint, (c) openapi.yaml's JobOperation enum.
	rootPath := findRepoRoot(t)
	apiHandlerSrc := readFile(t, rootPath+"/services/provider-registry-service/internal/api/jobs_handler.go")
	migrateSrc := readFile(t, rootPath+"/services/provider-registry-service/internal/migrate/migrate.go")
	openapiSrc := readFile(t, rootPath+"/contracts/api/llm-gateway/v1/openapi.yaml")

	for op := range visionJobOperations {
		quoted := `"` + op + `"`
		yamlEntry := "        - " + op
		sqlQuoted := `'` + op + `'`
		if !strings.Contains(apiHandlerSrc, quoted) {
			t.Errorf("vision op %q missing from jobs_handler.go validJobOperations — submit would fail with LLM_INVALID_REQUEST", op)
		}
		if !strings.Contains(migrateSrc, sqlQuoted) {
			t.Errorf("vision op %q missing from migrate.go CHECK constraint — INSERT would fail (LLM_INTERNAL_ERROR)", op)
		}
		if !strings.Contains(openapiSrc, yamlEntry) {
			t.Errorf("vision op %q missing from openapi.yaml JobOperation enum — contract drift", op)
		}
	}
}

// ── classifyVisionError matrix ────────────────────────────────────────

func TestClassifyVisionError_Cancelled(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	code, status := classifyVisionError(ctx, errors.New("any"))
	if code != "LLM_CANCELLED" || status != "cancelled" {
		t.Errorf("got (%s,%s), want (LLM_CANCELLED, cancelled)", code, status)
	}
}

func TestClassifyVisionError_DeadlineExceeded(t *testing.T) {
	ctx, cancel := context.WithDeadline(context.Background(), timeInPast())
	defer cancel()
	code, status := classifyVisionError(ctx, errors.New("any"))
	if code != "LLM_TIMEOUT" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_TIMEOUT, failed)", code, status)
	}
}

func TestClassifyVisionError_InvalidParams(t *testing.T) {
	code, status := classifyVisionError(context.Background(), provider.ErrVisionInvalidParams)
	if code != "LLM_INVALID_REQUEST" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_INVALID_REQUEST, failed)", code, status)
	}
}

func TestClassifyVisionError_InvalidParams_Wrapped(t *testing.T) {
	wrapped := wrapErr(provider.ErrVisionInvalidParams)
	code, _ := classifyVisionError(context.Background(), wrapped)
	if code != "LLM_INVALID_REQUEST" {
		t.Errorf("wrapped ErrVisionInvalidParams: got %s, want LLM_INVALID_REQUEST", code)
	}
}

func TestClassifyVisionError_CaptionFailed(t *testing.T) {
	code, status := classifyVisionError(context.Background(), provider.ErrVisionCaptionFailed)
	if code != "LLM_VISION_CAPTION_FAILED" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_VISION_CAPTION_FAILED, failed)", code, status)
	}
}

func TestClassifyVisionError_OperationNotSupported(t *testing.T) {
	code, status := classifyVisionError(context.Background(), provider.ErrOperationNotSupported)
	if code != "LLM_OPERATION_NOT_SUPPORTED" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_OPERATION_NOT_SUPPORTED, failed)", code, status)
	}
}

func TestClassifyVisionError_GenericMapsToUpstream(t *testing.T) {
	code, status := classifyVisionError(context.Background(), errors.New("upstream blew up"))
	if code != "LLM_UPSTREAM_ERROR" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_UPSTREAM_ERROR, failed)", code, status)
	}
}

func TestClassifyVisionError_RateLimitedTyped(t *testing.T) {
	rl := &provider.ErrUpstreamRateLimited{StatusCode: 429, Body: "slow"}
	code, status := classifyVisionError(context.Background(), rl)
	if code != "LLM_RATE_LIMITED" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_RATE_LIMITED, failed)", code, status)
	}
}

func TestClassifyVisionError_AuthFailedFrom401(t *testing.T) {
	perm := &provider.ErrUpstreamPermanent{StatusCode: 401, Body: "bad key"}
	code, status := classifyVisionError(context.Background(), perm)
	if code != "LLM_AUTH_FAILED" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_AUTH_FAILED, failed)", code, status)
	}
}

func TestClassifyVisionError_Permanent400IsUpstreamError(t *testing.T) {
	perm := &provider.ErrUpstreamPermanent{StatusCode: 400, Body: "bad input"}
	code, status := classifyVisionError(context.Background(), perm)
	if code != "LLM_UPSTREAM_ERROR" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_UPSTREAM_ERROR, failed)", code, status)
	}
}

func TestClassifyVisionError_Transient5xx(t *testing.T) {
	trans := &provider.ErrUpstreamTransient{StatusCode: 502, Body: "bad gateway"}
	code, status := classifyVisionError(context.Background(), trans)
	if code != "LLM_UPSTREAM_ERROR" || status != "failed" {
		t.Errorf("got (%s,%s), want (LLM_UPSTREAM_ERROR, failed)", code, status)
	}
}
