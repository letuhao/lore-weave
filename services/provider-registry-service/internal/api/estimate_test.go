package api

// Unit tests for the S5a pricing-oracle core (estimateItems). No DB: the pricer
// is a fake satisfying the modelPricer interface.

import (
	"context"
	"errors"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/provider-registry-service/internal/billing"
)

// fakePricer maps a model_ref UUID → its (pricing, found). A nil entry value
// means "found but empty pricing" (drives the unpriced path).
type fakePricer struct {
	byRef map[uuid.UUID]billing.Pricing
	known map[uuid.UUID]bool
	err   error // when set, every lookup returns this (infra-error path)
}

func (f fakePricer) ModelPricing(_ context.Context, _ string, _ uuid.UUID, ref uuid.UUID) (billing.Pricing, bool, error) {
	if f.err != nil {
		return billing.Pricing{}, false, f.err
	}
	if !f.known[ref] {
		return billing.Pricing{}, false, nil
	}
	return f.byRef[ref], true, nil
}

func TestEstimateItems_PricedTextAndEmbedding(t *testing.T) {
	textRef := uuid.New()
	embRef := uuid.New()
	pricer := fakePricer{
		known: map[uuid.UUID]bool{textRef: true, embRef: true},
		byRef: map[uuid.UUID]billing.Pricing{
			// $1/Mtok in, $10/Mtok out.
			textRef: {InputPerMTok: ptr(1.0), OutputPerMTok: ptr(10.0)},
			// $0.10/Mtok in (embedding, input-only).
			embRef: {InputPerMTok: ptr(0.10)},
		},
	}
	items := []estimateItem{
		{Label: "translation", ModelSource: "user_model", ModelRef: textRef.String(), Dimension: "text", InputTokens: 1_000_000, OutputTokens: 1_000_000},
		{Label: "embedding", ModelSource: "user_model", ModelRef: embRef.String(), Dimension: "input_only", InputTokens: 1_000_000, OutputTokens: 0},
	}
	out, err := estimateItems(context.Background(), pricer, uuid.New(), items)
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if len(out) != 2 {
		t.Fatalf("want 2 results, got %d", len(out))
	}
	// 1M in × $1/M + 1M out × $10/M = $11.
	if out[0].Status != estStatusOK || out[0].EstimatedUSD != 11.0 {
		t.Fatalf("translation: got %+v want ok/$11", out[0])
	}
	// embedding input-only: 1M × $0.10/M = $0.10; output dimension ignored even though absent.
	if out[1].Status != estStatusOK || out[1].EstimatedUSD != 0.10 {
		t.Fatalf("embedding: got %+v want ok/$0.10", out[1])
	}
}

func TestEstimateItems_Unpriced(t *testing.T) {
	// A text item against a model whose pricing lacks OutputPerMTok → unpriced.
	ref := uuid.New()
	pricer := fakePricer{
		known: map[uuid.UUID]bool{ref: true},
		byRef: map[uuid.UUID]billing.Pricing{ref: {InputPerMTok: ptr(1.0)}}, // no output dim
	}
	out, err := estimateItems(context.Background(), pricer, uuid.New(),
		[]estimateItem{{Label: "verify", ModelSource: "user_model", ModelRef: ref.String(), Dimension: "text", InputTokens: 100, OutputTokens: 100}})
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if out[0].Status != estStatusUnpriced || out[0].EstimatedUSD != 0 {
		t.Fatalf("got %+v want unpriced/$0", out[0])
	}
}

func TestEstimateItems_NotFound(t *testing.T) {
	pricer := fakePricer{known: map[uuid.UUID]bool{}} // nothing known
	out, err := estimateItems(context.Background(), pricer, uuid.New(),
		[]estimateItem{{Label: "extraction", ModelSource: "user_model", ModelRef: uuid.New().String(), Dimension: "text", InputTokens: 100, OutputTokens: 50}})
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if out[0].Status != estStatusNotFound {
		t.Fatalf("got %+v want not_found", out[0])
	}
}

func TestEstimateItems_BadModelRef(t *testing.T) {
	pricer := fakePricer{known: map[uuid.UUID]bool{}}
	out, err := estimateItems(context.Background(), pricer, uuid.New(),
		[]estimateItem{{Label: "x", ModelSource: "user_model", ModelRef: "not-a-uuid", Dimension: "text", InputTokens: 1}})
	if err != nil {
		t.Fatalf("unexpected err: %v", err)
	}
	if out[0].Status != estStatusBadRequest {
		t.Fatalf("got %+v want bad_request", out[0])
	}
}

func TestEstimateItems_BadModelSourceIsSoftPerItem(t *testing.T) {
	// review-impl #3: an unknown model_source must NOT nuke the whole batch
	// (ModelPricing hard-errors on it) — it's a per-item bad_request. The pricer
	// must never be reached for the bad item, so a nil-map pricer is safe here.
	out, err := estimateItems(context.Background(), fakePricer{}, uuid.New(),
		[]estimateItem{{Label: "x", ModelSource: "bogus", ModelRef: uuid.New().String(), Dimension: "text", InputTokens: 1, OutputTokens: 1}})
	if err != nil {
		t.Fatalf("bad source must be soft per-item, not a request error: %v", err)
	}
	if out[0].Status != estStatusBadRequest {
		t.Fatalf("got %+v want bad_request", out[0])
	}
}

func TestEstimateItems_InfraErrorPropagates(t *testing.T) {
	pricer := fakePricer{err: errors.New("db down")}
	_, err := estimateItems(context.Background(), pricer, uuid.New(),
		[]estimateItem{{Label: "x", ModelSource: "user_model", ModelRef: uuid.New().String(), Dimension: "text", InputTokens: 1, OutputTokens: 1}})
	if err == nil {
		t.Fatal("expected the pricer infra error to propagate (→ caller 500/502), got nil")
	}
}

func TestEstimateItems_EmptyBatch(t *testing.T) {
	out, err := estimateItems(context.Background(), fakePricer{}, uuid.New(), nil)
	if err != nil || len(out) != 0 {
		t.Fatalf("empty batch: got %v / %d", err, len(out))
	}
}
