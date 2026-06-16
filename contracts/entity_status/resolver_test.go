package entity_status

import (
	"context"
	"errors"
	"testing"
	"time"
)

// fakeReader implements each *Reader interface with a fixed response.
type fakeReader struct {
	res LookupResult
	err error
}

func (f *fakeReader) LookupByEntity(_ context.Context, _ EntityRef) (LookupResult, error) {
	return f.res, f.err
}
func (f *fakeReader) LookupByReality(_ context.Context, _ string) (LookupResult, error) {
	return f.res, f.err
}

func sampleRef() EntityRef {
	return EntityRef{
		EntityID:      "11111111-2222-3333-4444-555555555555",
		AggregateType: "pc",
		RealityID:     "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
	}
}

func fixedTime() time.Time {
	return time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
}

func TestEntityRefValidate(t *testing.T) {
	if err := sampleRef().Validate(); err != nil {
		t.Fatalf("valid ref: %v", err)
	}
	bad := sampleRef()
	bad.EntityID = ""
	if err := bad.Validate(); err == nil {
		t.Fatal("empty entity_id must error")
	}
	bad2 := sampleRef()
	bad2.AggregateType = ""
	if err := bad2.Validate(); err == nil {
		t.Fatal("empty aggregate_type must error")
	}
	bad3 := sampleRef()
	bad3.RealityID = ""
	if err := bad3.Validate(); err == nil {
		t.Fatal("empty reality_id must error")
	}
}

func TestResolverShortCircuitOnUserErased(t *testing.T) {
	r := &Resolver{
		PIIKek:          &fakeReader{res: LookupResult{Has: true, State: StateUserErased}},
		RealityRegistry: &fakeReader{res: LookupResult{}},
		Projections:     &fakeReader{},
		Now:             fixedTime,
	}
	env, err := r.GetEntityStatus(context.Background(), sampleRef())
	if err != nil {
		t.Fatal(err)
	}
	if env.State != StateUserErased {
		t.Fatalf("state=%q want user_erased", env.State)
	}
	if env.SourceLayer != "pii_kek" {
		t.Fatalf("source=%q want pii_kek", env.SourceLayer)
	}
	if env.EnvelopeVersion != 1 {
		t.Fatalf("envelope_version=%d want 1", env.EnvelopeVersion)
	}
}

func TestResolverShortCircuitOnDroppedReality(t *testing.T) {
	r := &Resolver{
		PIIKek:          nil,
		RealityRegistry: &fakeReader{res: LookupResult{Has: true, State: StateDropped}},
		Projections:     &fakeReader{},
		Now:             fixedTime,
	}
	env, err := r.GetEntityStatus(context.Background(), sampleRef())
	if err != nil {
		t.Fatal(err)
	}
	if env.State != StateDropped {
		t.Fatalf("state=%q want dropped", env.State)
	}
	if env.SourceLayer != "reality_registry" {
		t.Fatalf("source=%q", env.SourceLayer)
	}
}

func TestResolverFallsToProjections(t *testing.T) {
	r := &Resolver{
		PIIKek:          nil,
		RealityRegistry: &fakeReader{res: LookupResult{Has: true, State: StateActive}},
		RealityAncestry: nil,
		Projections:     &fakeReader{res: LookupResult{Has: true, State: StateActive, AggregateVersion: 17}},
		Now:             fixedTime,
	}
	env, err := r.GetEntityStatus(context.Background(), sampleRef())
	if err != nil {
		t.Fatal(err)
	}
	if env.State != StateActive {
		t.Fatalf("state=%q want active", env.State)
	}
	if env.SourceLayer != "projections" {
		t.Fatalf("source=%q want projections", env.SourceLayer)
	}
	if env.AggregateVersion != 17 {
		t.Fatalf("aggregate_version=%d", env.AggregateVersion)
	}
}

func TestResolverProjectionMissingPromotesToDropped(t *testing.T) {
	r := &Resolver{
		RealityRegistry: &fakeReader{res: LookupResult{Has: true, State: StateActive}},
		Projections:     &fakeReader{res: LookupResult{Has: false}},
		Now:             fixedTime,
	}
	env, err := r.GetEntityStatus(context.Background(), sampleRef())
	if err != nil {
		t.Fatal(err)
	}
	if env.State != StateDropped {
		t.Fatalf("missing projection -> dropped; got %q", env.State)
	}
}

func TestResolverPropagatesReaderErrors(t *testing.T) {
	r := &Resolver{
		PIIKek:          &fakeReader{err: errors.New("kms down")},
		RealityRegistry: &fakeReader{},
		Projections:     &fakeReader{},
		Now:             fixedTime,
	}
	if _, err := r.GetEntityStatus(context.Background(), sampleRef()); err == nil {
		t.Fatal("expected error")
	}
}

func TestResolverRequiresMandatoryReaders(t *testing.T) {
	r := &Resolver{}
	if _, err := r.GetEntityStatus(context.Background(), sampleRef()); err == nil {
		t.Fatal("missing readers must error")
	}
}

func TestResolverCompoundReducesAncestryAndRegistry(t *testing.T) {
	// reality archived + entity severed -> severed wins via Reduce
	// (severed has rank 3, archived has rank 2).
	r := &Resolver{
		RealityRegistry: &fakeReader{res: LookupResult{Has: true, State: StateArchived}},
		RealityAncestry: &fakeReader{res: LookupResult{Has: true, State: StateSevered}},
		Projections:     &fakeReader{},
		Now:             fixedTime,
	}
	env, err := r.GetEntityStatus(context.Background(), sampleRef())
	if err != nil {
		t.Fatal(err)
	}
	if env.State != StateSevered {
		t.Fatalf("compound -> severed; got %q", env.State)
	}
}

// ── CachedResolver ─────────────────────────────────────────────────────────

type memCache struct {
	store map[string]EntityStatusEnvelope
}

func newMemCache() *memCache { return &memCache{store: map[string]EntityStatusEnvelope{}} }

func key(ref EntityRef) string {
	return ref.RealityID + ":" + ref.AggregateType + ":" + ref.EntityID
}

func (m *memCache) Get(_ context.Context, ref EntityRef) (EntityStatusEnvelope, bool, error) {
	env, ok := m.store[key(ref)]
	return env, ok, nil
}

func (m *memCache) Set(_ context.Context, ref EntityRef, env EntityStatusEnvelope, _ time.Duration) error {
	m.store[key(ref)] = env
	return nil
}

func TestCachedResolverHitsCacheOnSecondCall(t *testing.T) {
	count := 0
	proj := readerFunc(func(_ context.Context, _ EntityRef) (LookupResult, error) {
		count++
		return LookupResult{Has: true, State: StateActive, AggregateVersion: 1}, nil
	})
	r := &Resolver{
		RealityRegistry: &fakeReader{res: LookupResult{Has: true, State: StateActive}},
		Projections:     proj,
		Now:             fixedTime,
	}
	c := &CachedResolver{
		Reader:   newMemCache(),
		Writer:   nil, // intentionally nil; we'll set below
		Resolver: r,
	}
	mc := newMemCache()
	c.Reader = mc
	c.Writer = mc
	if _, err := c.GetEntityStatus(context.Background(), sampleRef()); err != nil {
		t.Fatal(err)
	}
	if _, err := c.GetEntityStatus(context.Background(), sampleRef()); err != nil {
		t.Fatal(err)
	}
	if count != 1 {
		t.Fatalf("projection invoked %d times; want 1 (cache hit on 2nd call)", count)
	}
}

// readerFunc lets us inline ProjectionReader behavior in one test.
type readerFunc func(context.Context, EntityRef) (LookupResult, error)

func (f readerFunc) LookupByEntity(ctx context.Context, ref EntityRef) (LookupResult, error) {
	return f(ctx, ref)
}
