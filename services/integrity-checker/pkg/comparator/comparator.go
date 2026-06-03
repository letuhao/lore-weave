// Package comparator re-derives the expected projection state for a
// sampled aggregate by replaying events through an AggregateLoader, then
// performs a BYTE-EQUAL JSON diff against the projection row's payload.
//
// CRITICAL REUSE: this comparator does NOT re-implement state derivation —
// the AggregateLoader interface is the Go-side projection of the Rust
// `dp_kernel::load_aggregate` function (cycle-12). Live wiring connects
// the Rust crate to this interface via FFI or sibling service call; cycle-15
// ships the IN-MEMORY fake (InMemLoader) so the orchestrator can be
// unit-tested without the Rust crate.
//
// CRITICAL: drift detection is BYTE-EQUAL (after canonical JSON
// normalization) — NOT approximate / NOT semantic. The whole point of the
// integrity-checker is to catch the cases where the projection runner
// produced different output than the replay would. Approximate matching
// would mask real bugs.
package comparator

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"time"

	"github.com/loreweave/foundation/services/integrity-checker/pkg/sampler"
	"github.com/loreweave/foundation/services/integrity-checker/pkg/types"
)

// AggregateLoader is the Go-side mirror of `dp_kernel::load_aggregate`
// (cycle-12). Given (reality_id, aggregate_type, aggregate_id), returns the
// canonical JSON of the aggregate state AT the projection row's version.
//
// Production wires this to a sibling service (e.g. world-service replay
// endpoint) or to a Rust FFI binding. Tests inject InMemLoader.
//
// SEMANTICS — MUST MATCH cycle-12 load_aggregate:
//   - cache MUST be bypassed (None passed to load_aggregate). Integrity
//     check is supposed to hit source-of-truth (events) not cache.
//   - load returns the state AT max(aggregate_version) ≤ targetVersion.
//     The comparator passes the projection row's aggregate_version so the
//     replay stops at the same point the projection THINKS it is.
//   - On error (events missing, snapshot deserialize failure), the
//     comparator marks the sample SKIPPED (not DRIFTED) — missing events
//     are an integrity issue in their own right but distinct from
//     projection-vs-replay drift.
type AggregateLoader interface {
	LoadAt(
		ctx context.Context,
		realityID interface{},
		aggregateType string,
		aggregateID string,
		targetVersion uint64,
	) ([]byte, error)
}

// Comparator is the orchestrator helper.
type Comparator struct {
	loader AggregateLoader
	clock  func() time.Time
}

// Config is the constructor input.
type Config struct {
	Loader AggregateLoader
	Clock  func() time.Time // tests inject; production passes time.Now
}

// New constructs a Comparator.
func New(c Config) (*Comparator, error) {
	if c.Loader == nil {
		return nil, errors.New("comparator: AggregateLoader nil")
	}
	if c.Clock == nil {
		return nil, errors.New("comparator: Clock nil")
	}
	return &Comparator{loader: c.Loader, clock: c.Clock}, nil
}

// CompareOne runs the comparator against one sampled aggregate.
// Returns SampleResult with Drifted=true/false/Skipped.
//
// `projectionRow.PayloadJSON` MUST be the projection's serialized state
// (jsonb_build_object of all non-meta cols, canonicalized). The
// AggregateLoader returns the replay's serialized state in the SAME
// canonical form.
func (c *Comparator) CompareOne(
	ctx context.Context,
	ref types.AggregateRef,
	projectionPayload []byte,
) types.SampleResult {
	res := types.SampleResult{
		Ref:       ref,
		CheckedAt: c.clock(),
	}
	replayBytes, err := c.loader.LoadAt(ctx, ref.RealityID, ref.AggregateType, ref.AggregateID, ref.AggregateVersion)
	if err != nil {
		res.Skipped = true
		res.SkipReason = fmt.Sprintf("loader error: %v", err)
		return res
	}
	// Canonicalize both sides; drift = byte-not-equal.
	want, err := canonicalize(replayBytes)
	if err != nil {
		res.Skipped = true
		res.SkipReason = fmt.Sprintf("replay canonicalize: %v", err)
		return res
	}
	got, err := canonicalize(projectionPayload)
	if err != nil {
		res.Skipped = true
		res.SkipReason = fmt.Sprintf("projection canonicalize: %v", err)
		return res
	}
	if !bytes.Equal(want, got) {
		res.Drifted = true
		res.Reason = fmt.Sprintf("byte-equal diff @v%d: replay_bytes=%d projection_bytes=%d",
			ref.AggregateVersion, len(want), len(got))
	}
	return res
}

// Canonicalize is the exported form of [canonicalize] — re-serialize a JSON
// value with sorted keys + stripped whitespace, so two semantically-equal JSON
// documents compare byte-equal. The live L3.E checker (pkg/live) uses it to
// compare a replayed row's `to_jsonb - meta` against the live row's; both go
// through Postgres `to_jsonb`, so this only needs to reconcile key ordering.
func Canonicalize(in []byte) ([]byte, error) { return canonicalize(in) }

// canonicalize re-serializes a JSON value with sorted keys + stripped
// whitespace. Returns the input unchanged on parse errors of NON-OBJECT
// JSON (numbers, strings, arrays) — only objects need key-sort. Arrays
// are walked recursively so nested objects within arrays are canonicalized.
func canonicalize(in []byte) ([]byte, error) {
	if len(in) == 0 {
		return []byte("null"), nil
	}
	var raw interface{}
	dec := json.NewDecoder(bytes.NewReader(in))
	dec.UseNumber() // preserve int vs float distinction
	if err := dec.Decode(&raw); err != nil {
		return nil, fmt.Errorf("canonicalize: decode: %w", err)
	}
	return marshalCanonical(raw)
}

func marshalCanonical(v interface{}) ([]byte, error) {
	switch x := v.(type) {
	case map[string]interface{}:
		keys := make([]string, 0, len(x))
		for k := range x {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		var buf bytes.Buffer
		buf.WriteByte('{')
		for i, k := range keys {
			if i > 0 {
				buf.WriteByte(',')
			}
			kb, err := json.Marshal(k)
			if err != nil {
				return nil, err
			}
			buf.Write(kb)
			buf.WriteByte(':')
			vb, err := marshalCanonical(x[k])
			if err != nil {
				return nil, err
			}
			buf.Write(vb)
		}
		buf.WriteByte('}')
		return buf.Bytes(), nil
	case []interface{}:
		var buf bytes.Buffer
		buf.WriteByte('[')
		for i, item := range x {
			if i > 0 {
				buf.WriteByte(',')
			}
			ib, err := marshalCanonical(item)
			if err != nil {
				return nil, err
			}
			buf.Write(ib)
		}
		buf.WriteByte(']')
		return buf.Bytes(), nil
	default:
		return json.Marshal(v)
	}
}

// InMemLoader is the test fake. Maps (reality, aggregate_type,
// aggregate_id, version) → payload bytes.
type InMemLoader struct {
	rows map[string][]byte
	err  error
}

// NewInMemLoader returns an empty fake.
func NewInMemLoader() *InMemLoader {
	return &InMemLoader{rows: make(map[string][]byte)}
}

// SetErr forces all subsequent LoadAt calls to return this error
// (used for testing the SKIPPED path).
func (f *InMemLoader) SetErr(err error) { f.err = err }

// AddState registers a replay result for one aggregate version.
func (f *InMemLoader) AddState(realityID interface{}, aggregateType, aggregateID string, version uint64, payload []byte) {
	key := fmt.Sprintf("%v|%s|%s|%d", realityID, aggregateType, aggregateID, version)
	f.rows[key] = payload
}

// LoadAt returns the registered payload or an error.
func (f *InMemLoader) LoadAt(_ context.Context, realityID interface{}, aggregateType, aggregateID string, version uint64) ([]byte, error) {
	if f.err != nil {
		return nil, f.err
	}
	key := fmt.Sprintf("%v|%s|%s|%d", realityID, aggregateType, aggregateID, version)
	p, ok := f.rows[key]
	if !ok {
		return nil, fmt.Errorf("InMemLoader: no state for %s", key)
	}
	return p, nil
}

// Compile-time check that the sampler types are visible (avoid unused
// import; the package depends on sampler.ProjectionRow indirectly via
// callers but a direct symbol reference here documents the relationship
// for future maintainers).
var _ = sampler.ProjectionRow{}
