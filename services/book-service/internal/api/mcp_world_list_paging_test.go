package api

// K25 (2026-07-24) — OUT-5: world_list must not silently truncate.
//
// It capped at `limit` (default 20) but returned ONLY the `worlds` slice — no total, no
// has_more, no is_complete. A caller with 27 worlds asking limit=20 read the result as "you
// have 20 worlds": a silent truncation, the exact failure OUT-5 forbids ("reads to the agent
// as 'this is everything' when it isn't"). world_list now carries the same paging envelope +
// prose stop-signal as book_list (the shared listPage helper).
//
// DB-gated (dbTestServer), like the other world happy-path tests.

import (
	"testing"

	"github.com/google/uuid"
)

func TestToolWorldList_ReportsPartialityWhenCapped_DB(t *testing.T) {
	s, _ := dbTestServer(t)
	owner := uuid.New()
	ctx := identityCtxForTest(t, owner)

	// Seed 3 worlds, then list with limit=2 → the result MUST say there is a third.
	for _, name := range []string{"Aethelmoor", "Brightwater", "Cinderfell"} {
		if _, _, err := s.toolWorldCreate(ctx, nil, worldCreateIn{Name: name}); err != nil {
			t.Fatalf("seed world %q: %v", name, err)
		}
	}

	_, out, err := s.toolWorldList(ctx, nil, worldListIn{Limit: 2})
	if err != nil {
		t.Fatalf("world_list: %v", err)
	}

	if len(out.Worlds) != 2 {
		t.Fatalf("limit=2 must return 2 worlds, got %d", len(out.Worlds))
	}
	if out.Total != 3 {
		t.Fatalf("total must be the TRUE count (3), got %d — the agent needs the real size", out.Total)
	}
	if !out.Page.HasMore || out.Page.IsComplete {
		t.Fatalf("a capped list must NOT read as complete: has_more=%v is_complete=%v",
			out.Page.HasMore, out.Page.IsComplete)
	}
	if out.Page.NextOffset == nil || *out.Page.NextOffset != 2 {
		t.Fatalf("next_offset must point past the returned slice (2), got %v", out.Page.NextOffset)
	}
	if out.Guidance == "" {
		t.Fatal("a capped list must carry a prose stop/continue signal for a weak model")
	}
}

func TestToolWorldList_IsCompleteWhenAllFit_DB(t *testing.T) {
	// The other half: when nothing is dropped, the result must AFFIRMATIVELY say so, or a
	// cautious agent keeps paging an already-complete list.
	s, _ := dbTestServer(t)
	owner := uuid.New()
	ctx := identityCtxForTest(t, owner)

	for _, name := range []string{"Solitude", "Second"} {
		if _, _, err := s.toolWorldCreate(ctx, nil, worldCreateIn{Name: name}); err != nil {
			t.Fatalf("seed: %v", err)
		}
	}

	_, out, err := s.toolWorldList(ctx, nil, worldListIn{Limit: 20})
	if err != nil {
		t.Fatalf("world_list: %v", err)
	}
	if out.Total != 2 || len(out.Worlds) != 2 {
		t.Fatalf("expected 2/2, got total=%d returned=%d", out.Total, len(out.Worlds))
	}
	if out.Page.HasMore || !out.Page.IsComplete {
		t.Fatalf("a full page must read as complete: has_more=%v is_complete=%v",
			out.Page.HasMore, out.Page.IsComplete)
	}
	if out.Page.NextOffset != nil {
		t.Fatalf("a complete list must not offer a next_offset, got %v", out.Page.NextOffset)
	}
}
