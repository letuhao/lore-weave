package prompt

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/google/uuid"
)

// ─────────────────────────────────────────────────────────────────────────
// Test helpers.
// ─────────────────────────────────────────────────────────────────────────

func newCacheForTest(t *testing.T) (*Cache, *FakeBackend, *FixedClock, *FakeMetrics) {
	t.Helper()
	clk := NewFixedClock(time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC))
	be := NewFakeBackend(clk)
	met := NewFakeMetrics()
	c, err := New(Config{Backend: be, TTL: 60 * time.Second, Clock: clk, Metrics: met})
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	return c, be, clk, met
}

func sampleEntry(realityID uuid.UUID, attribute string) CacheEntry {
	return CacheEntry{
		RealityID:     realityID,
		CanonEntryID:  uuid.New(),
		BookID:        uuid.New(),
		AttributePath: attribute,
		Value:         []byte(`{"name":"Aldarion"}`),
		CanonLayer:    "L2_seeded",
		LastSyncedAt:  time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC),
	}
}

// ─────────────────────────────────────────────────────────────────────────
// Tests.
// ─────────────────────────────────────────────────────────────────────────

func TestNew_RejectsMissingBackend(t *testing.T) {
	_, err := New(Config{})
	if err == nil {
		t.Fatal("expected error for missing Backend")
	}
}

func TestNew_DefaultsApplied(t *testing.T) {
	be := NewFakeBackend(nil)
	c, err := New(Config{Backend: be})
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	if c.ttl != DefaultTTL {
		t.Fatalf("default TTL not applied: got %v want %v", c.ttl, DefaultTTL)
	}
	if c.codec == nil {
		t.Fatal("default Codec missing")
	}
	if c.metrics == nil {
		t.Fatal("default MetricsSink missing")
	}
}

func TestIsAttributeCacheable_Whitelist(t *testing.T) {
	cases := []struct {
		path string
		want bool
	}{
		{"world.climate", true},
		{"faction.allegiance", true},
		{"character.eye_color", true},
		{"rule.combat.crit_chance", true},
		{"lore.region.weather", true},
		// NOT cacheable:
		{"chapter.prose.body", false},
		{"history.recent.events", false},
		{"raw.text", false},
		{"", false},
		{"world", false}, // missing the dot — not a prefix match
	}
	for _, tc := range cases {
		t.Run(tc.path, func(t *testing.T) {
			if got := IsAttributeCacheable(tc.path); got != tc.want {
				t.Fatalf("IsAttributeCacheable(%q) = %v, want %v", tc.path, got, tc.want)
			}
		})
	}
}

func TestBuildKey_PerRealityIsolation(t *testing.T) {
	r1 := uuid.New()
	r2 := uuid.New()
	bookID := uuid.New()
	k1 := BuildKey(r1, bookID, "world.climate")
	k2 := BuildKey(r2, bookID, "world.climate")
	if k1 == k2 {
		t.Fatal("Q-L5-1 per-reality isolation BROKEN: same key across realities")
	}
	if got := fmt.Sprintf("canon:%s:%s:world.climate", r1, bookID); k1 != got {
		t.Fatalf("BuildKey shape drift: got %s want %s", k1, got)
	}
}

func TestSet_RejectsNonCacheableAttribute(t *testing.T) {
	c, _, _, _ := newCacheForTest(t)
	entry := sampleEntry(uuid.New(), "chapter.prose.body")
	err := c.Set(context.Background(), entry)
	if !errors.Is(err, ErrAttributeNotCacheable) {
		t.Fatalf("expected ErrAttributeNotCacheable, got %v", err)
	}
}

func TestGet_RejectsNonCacheableAttribute(t *testing.T) {
	c, _, _, _ := newCacheForTest(t)
	_, err := c.Get(context.Background(), uuid.New(), uuid.New(), "chapter.prose.body")
	if !errors.Is(err, ErrAttributeNotCacheable) {
		t.Fatalf("expected ErrAttributeNotCacheable, got %v", err)
	}
}

func TestGet_MissReturnsErrCacheMiss(t *testing.T) {
	c, _, _, met := newCacheForTest(t)
	realityID := uuid.New()
	_, err := c.Get(context.Background(), realityID, uuid.New(), "world.climate")
	if !errors.Is(err, ErrCacheMiss) {
		t.Fatalf("expected ErrCacheMiss, got %v", err)
	}
	if met.Misses[realityID] != 1 {
		t.Fatalf("miss counter not incremented: got %d", met.Misses[realityID])
	}
}

func TestSetThenGet_HitFlow(t *testing.T) {
	c, _, _, met := newCacheForTest(t)
	realityID := uuid.New()
	entry := sampleEntry(realityID, "world.climate")
	if err := c.Set(context.Background(), entry); err != nil {
		t.Fatalf("Set: %v", err)
	}
	got, err := c.Get(context.Background(), realityID, entry.BookID, entry.AttributePath)
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if got.CanonEntryID != entry.CanonEntryID {
		t.Fatalf("entry id mismatch")
	}
	if string(got.Value) != string(entry.Value) {
		t.Fatalf("value mismatch")
	}
	if got.CanonLayer != "L2_seeded" {
		t.Fatalf("Q-L5-3 canon_layer drift: got %s", got.CanonLayer)
	}
	if met.Hits[realityID] != 1 {
		t.Fatalf("hit counter not incremented")
	}
	if got.ExpiresAt.IsZero() {
		t.Fatal("ExpiresAt not populated on stored entry (Q-L5-1 TTL fallback)")
	}
}

func TestTTLFallback_ExpiredEntryIsMiss(t *testing.T) {
	// Q-L5-1: TTL is FALLBACK only — but it MUST work for crash-recovery.
	c, be, clk, met := newCacheForTest(t)
	realityID := uuid.New()
	entry := sampleEntry(realityID, "faction.allegiance")
	if err := c.Set(context.Background(), entry); err != nil {
		t.Fatalf("Set: %v", err)
	}

	// Advance past TTL (60s default + 1s margin).
	clk.Advance(61 * time.Second)

	_, err := c.Get(context.Background(), realityID, entry.BookID, entry.AttributePath)
	if !errors.Is(err, ErrCacheMiss) {
		t.Fatalf("expected ErrCacheMiss after TTL, got %v", err)
	}
	// Cleanup: backend should no longer hold the key after a stale Get.
	if be.Size() != 0 {
		t.Fatalf("expired key not cleaned: backend size=%d", be.Size())
	}
	if met.Misses[realityID] != 1 {
		t.Fatalf("miss not counted")
	}
}

func TestInvalidate_PrimaryPath_EventDriven(t *testing.T) {
	// Q-L5-1 PRIMARY: Invalidate(realityID, canonEntryID) removes ALL
	// cache rows for that canon entry in that reality.
	c, be, _, met := newCacheForTest(t)
	realityID := uuid.New()
	bookID := uuid.New()

	// Populate 3 attributes for the SAME canon_entry across 1 reality.
	canonEntryID := uuid.New()
	for _, attr := range []string{"world.climate", "faction.allegiance", "lore.intro"} {
		e := sampleEntry(realityID, attr)
		e.BookID = bookID
		e.CanonEntryID = canonEntryID
		if err := c.Set(context.Background(), e); err != nil {
			t.Fatalf("Set %s: %v", attr, err)
		}
	}
	// And ONE unrelated canon entry in the same reality — must NOT be deleted.
	other := sampleEntry(realityID, "rule.combat.crit_chance")
	other.BookID = bookID
	if err := c.Set(context.Background(), other); err != nil {
		t.Fatalf("Set other: %v", err)
	}

	if be.Size() != 4 {
		t.Fatalf("setup wrong: size=%d want 4", be.Size())
	}

	deleted, err := c.Invalidate(context.Background(), realityID, canonEntryID)
	if err != nil {
		t.Fatalf("Invalidate: %v", err)
	}
	if deleted != 3 {
		t.Fatalf("Invalidate deleted=%d want 3", deleted)
	}
	if be.Size() != 1 {
		t.Fatalf("post-invalidate size=%d want 1 (only the other entry remains)", be.Size())
	}
	if met.Invalidations[realityID] != 3 {
		t.Fatalf("invalidation metric=%d want 3", met.Invalidations[realityID])
	}

	// Idempotent — second call deletes nothing.
	deleted2, err := c.Invalidate(context.Background(), realityID, canonEntryID)
	if err != nil {
		t.Fatalf("idempotent Invalidate: %v", err)
	}
	if deleted2 != 0 {
		t.Fatalf("idempotent Invalidate: deleted=%d want 0", deleted2)
	}
}

func TestInvalidate_PerRealityIsolation(t *testing.T) {
	// CRITICAL: invalidating a canon_entry in reality A must NOT touch
	// cache rows for the SAME canon_entry in reality B.
	c, _, _, _ := newCacheForTest(t)
	realityA := uuid.New()
	realityB := uuid.New()
	bookID := uuid.New()
	canonEntryID := uuid.New()

	for _, realityID := range []uuid.UUID{realityA, realityB} {
		e := sampleEntry(realityID, "world.climate")
		e.BookID = bookID
		e.CanonEntryID = canonEntryID
		if err := c.Set(context.Background(), e); err != nil {
			t.Fatalf("Set: %v", err)
		}
	}

	deleted, err := c.Invalidate(context.Background(), realityA, canonEntryID)
	if err != nil {
		t.Fatalf("Invalidate: %v", err)
	}
	if deleted != 1 {
		t.Fatalf("Invalidate deleted=%d want 1 (only reality A)", deleted)
	}

	// Reality B's cache row MUST survive.
	gotB, err := c.Get(context.Background(), realityB, bookID, "world.climate")
	if err != nil {
		t.Fatalf("reality B cache row lost: %v", err)
	}
	if gotB.RealityID != realityB {
		t.Fatalf("cross-reality leak: got %s expected %s", gotB.RealityID, realityB)
	}
}

func TestInvalidateReality_DropsAllRealityCache(t *testing.T) {
	c, be, _, _ := newCacheForTest(t)
	realityID := uuid.New()
	otherReality := uuid.New()

	// 5 entries in target reality + 1 in another reality.
	for _, attr := range []string{"world.climate", "world.geo", "faction.banner", "lore.intro", "rule.combat"} {
		if err := c.Set(context.Background(), sampleEntry(realityID, attr)); err != nil {
			t.Fatalf("Set: %v", err)
		}
	}
	if err := c.Set(context.Background(), sampleEntry(otherReality, "world.climate")); err != nil {
		t.Fatalf("Set other: %v", err)
	}

	deleted, err := c.InvalidateReality(context.Background(), realityID)
	if err != nil {
		t.Fatalf("InvalidateReality: %v", err)
	}
	if deleted != 5 {
		t.Fatalf("InvalidateReality deleted=%d want 5", deleted)
	}
	if be.Size() != 1 {
		t.Fatalf("post-invalidate size=%d want 1 (otherReality survives)", be.Size())
	}
}

func TestCodec_RoundTrip(t *testing.T) {
	entry := sampleEntry(uuid.New(), "world.climate")
	entry.ExpiresAt = time.Date(2026, 5, 29, 12, 1, 0, 0, time.UTC)
	raw, err := (JSONCodec{}).Encode(entry)
	if err != nil {
		t.Fatalf("Encode: %v", err)
	}
	out, err := (JSONCodec{}).Decode(raw)
	if err != nil {
		t.Fatalf("Decode: %v", err)
	}
	if out.CanonEntryID != entry.CanonEntryID {
		t.Fatalf("CanonEntryID drift")
	}
	if out.CanonLayer != entry.CanonLayer {
		t.Fatalf("Q-L5-3 CanonLayer drift")
	}
	if !out.ExpiresAt.Equal(entry.ExpiresAt) {
		t.Fatalf("ExpiresAt drift")
	}
	if string(out.Value) != string(entry.Value) {
		t.Fatalf("Value drift")
	}
}

func TestCacheEntry_CacheKeyShape(t *testing.T) {
	r := uuid.New()
	b := uuid.New()
	e := sampleEntry(r, "world.climate")
	e.BookID = b
	want := fmt.Sprintf("canon:%s:%s:world.climate", r, b)
	if got := e.CacheKey(); got != want {
		t.Fatalf("CacheKey drift: got %s want %s", got, want)
	}
}

// ─────────────────────────────────────────────────────────────────────────
// CanonReader tests (cache-aside flow).
// ─────────────────────────────────────────────────────────────────────────

// fakeReader is the cold-path Reader for canon_reader tests.
type fakeReader struct {
	rows  map[string]CanonValue
	calls int
}

func newFakeReader() *fakeReader { return &fakeReader{rows: map[string]CanonValue{}} }

func (f *fakeReader) ReadCanon(_ context.Context, realityID, bookID uuid.UUID, attributePath string) (CanonValue, error) {
	f.calls++
	v, ok := f.rows[BuildKey(realityID, bookID, attributePath)]
	if !ok {
		return CanonValue{}, ErrCanonNotFound
	}
	return v, nil
}

func TestCanonReader_HitsCacheOnSecondRead(t *testing.T) {
	cache, _, _, _ := newCacheForTest(t)
	rd := newFakeReader()
	realityID := uuid.New()
	bookID := uuid.New()
	val := CanonValue{
		CanonEntryID:  uuid.New(),
		RealityID:     realityID,
		BookID:        bookID,
		AttributePath: "world.climate",
		Value:         []byte(`{"climate":"arid"}`),
		CanonLayer:    "L1_axiom",
	}
	rd.rows[BuildKey(realityID, bookID, "world.climate")] = val

	cr, err := NewCanonReader(CanonReaderConfig{Cache: cache, Reader: rd})
	if err != nil {
		t.Fatalf("NewCanonReader: %v", err)
	}

	// First read = miss → reader.
	got1, err := cr.Read(context.Background(), realityID, bookID, "world.climate")
	if err != nil {
		t.Fatalf("first Read: %v", err)
	}
	if got1.FromCache {
		t.Fatal("first read should have FromCache=false (miss path)")
	}
	if rd.calls != 1 {
		t.Fatalf("reader calls=%d want 1", rd.calls)
	}

	// Second read = hit → cache.
	got2, err := cr.Read(context.Background(), realityID, bookID, "world.climate")
	if err != nil {
		t.Fatalf("second Read: %v", err)
	}
	if !got2.FromCache {
		t.Fatal("second read should have FromCache=true (cache hit)")
	}
	if rd.calls != 1 {
		t.Fatalf("reader calls=%d want 1 (no extra reader call on hit)", rd.calls)
	}
	if got2.CanonLayer != "L1_axiom" {
		t.Fatalf("Q-L5-3 layer not preserved through cache: got %s", got2.CanonLayer)
	}
}

func TestCanonReader_NotCacheable_AlwaysReader(t *testing.T) {
	cache, _, _, _ := newCacheForTest(t)
	rd := newFakeReader()
	realityID := uuid.New()
	bookID := uuid.New()
	val := CanonValue{RealityID: realityID, BookID: bookID, AttributePath: "chapter.prose.body", Value: []byte("..."), CanonLayer: "L2_seeded"}
	rd.rows[BuildKey(realityID, bookID, "chapter.prose.body")] = val

	cr, _ := NewCanonReader(CanonReaderConfig{Cache: cache, Reader: rd})

	for i := 0; i < 3; i++ {
		got, err := cr.Read(context.Background(), realityID, bookID, "chapter.prose.body")
		if err != nil {
			t.Fatalf("iter %d Read: %v", i, err)
		}
		if got.FromCache {
			t.Fatalf("iter %d: non-cacheable path should NEVER be FromCache=true", i)
		}
	}
	if rd.calls != 3 {
		t.Fatalf("reader calls=%d want 3 (no caching for non-cacheable path)", rd.calls)
	}
}

func TestCanonReader_NotFoundPropagates(t *testing.T) {
	cache, _, _, _ := newCacheForTest(t)
	rd := newFakeReader()
	cr, _ := NewCanonReader(CanonReaderConfig{Cache: cache, Reader: rd})
	_, err := cr.Read(context.Background(), uuid.New(), uuid.New(), "world.climate")
	if !errors.Is(err, ErrCanonNotFound) {
		t.Fatalf("expected ErrCanonNotFound, got %v", err)
	}
}

func TestCanonReader_Invalidate_ForcesReaderFetch(t *testing.T) {
	// Q-L5-1 PRIMARY: after Invalidate, next Read MUST hit the cold path.
	cache, _, _, _ := newCacheForTest(t)
	rd := newFakeReader()
	realityID := uuid.New()
	bookID := uuid.New()
	canonEntryID := uuid.New()
	val := CanonValue{
		CanonEntryID:  canonEntryID,
		RealityID:     realityID,
		BookID:        bookID,
		AttributePath: "world.climate",
		Value:         []byte(`{"v":1}`),
		CanonLayer:    "L2_seeded",
	}
	rd.rows[BuildKey(realityID, bookID, "world.climate")] = val

	cr, _ := NewCanonReader(CanonReaderConfig{Cache: cache, Reader: rd})

	// Warm.
	_, _ = cr.Read(context.Background(), realityID, bookID, "world.climate")
	if rd.calls != 1 {
		t.Fatalf("warm: reader calls=%d", rd.calls)
	}

	// Cached.
	_, _ = cr.Read(context.Background(), realityID, bookID, "world.climate")
	if rd.calls != 1 {
		t.Fatalf("cached: reader calls=%d", rd.calls)
	}

	// Invalidate.
	n, err := cr.Invalidate(context.Background(), realityID, canonEntryID)
	if err != nil {
		t.Fatalf("Invalidate: %v", err)
	}
	if n != 1 {
		t.Fatalf("Invalidate deleted=%d want 1", n)
	}

	// Now reader is hit again.
	rd.rows[BuildKey(realityID, bookID, "world.climate")] = CanonValue{
		CanonEntryID:  canonEntryID,
		RealityID:     realityID,
		BookID:        bookID,
		AttributePath: "world.climate",
		Value:         []byte(`{"v":2}`),
		CanonLayer:    "L2_seeded",
	}
	got, err := cr.Read(context.Background(), realityID, bookID, "world.climate")
	if err != nil {
		t.Fatalf("post-invalidate Read: %v", err)
	}
	if rd.calls != 2 {
		t.Fatalf("post-invalidate: reader calls=%d want 2", rd.calls)
	}
	if string(got.Value) != `{"v":2}` {
		t.Fatalf("stale value served after invalidate: got %s", got.Value)
	}
}

// ─────────────────────────────────────────────────────────────────────────
// Guardrail interface tests (Q-L5-5).
// ─────────────────────────────────────────────────────────────────────────

func TestNoOpGuardrail_Allows(t *testing.T) {
	var g CanonGuardrail = NoOpGuardrail{}
	err := g.CheckProposedWrite(context.Background(), GuardrailProposal{})
	if err != nil {
		t.Fatalf("NoOpGuardrail must allow, got %v", err)
	}
}

func TestStubRejectGuardrail_ReturnsViolation(t *testing.T) {
	var g CanonGuardrail = StubRejectGuardrail{Reason: "test reject"}
	err := g.CheckProposedWrite(context.Background(), GuardrailProposal{
		BookID:        uuid.New(),
		AttributePath: "world.climate",
		ProposedValue: []byte(`"tropical"`),
	})
	if err == nil {
		t.Fatal("expected violation, got nil")
	}
	var v *GuardrailViolation
	if !errors.As(err, &v) {
		t.Fatalf("expected *GuardrailViolation, got %T", err)
	}
	if v.Reason != "test reject" {
		t.Fatalf("reason drift: got %s", v.Reason)
	}
	if v.Axiom.CanonLayer != "L1_axiom" {
		t.Fatalf("violation axiom layer should be L1_axiom for guardrail rejections, got %s", v.Axiom.CanonLayer)
	}
}
