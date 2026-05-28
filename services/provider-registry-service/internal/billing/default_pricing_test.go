package billing

import "testing"

func TestDefaultPricing_KnownModel_PreFills(t *testing.T) {
	p, ok := DefaultPricing("openai", "gpt-4o-mini")
	if !ok {
		t.Fatal("expected gpt-4o-mini to be in the default table")
	}
	if p.InputPerMTok == nil || p.OutputPerMTok == nil {
		t.Fatal("known text model must have both text dimensions set")
	}
	if *p.InputPerMTok != 0.15 || *p.OutputPerMTok != 0.60 {
		t.Fatalf("gpt-4o-mini pricing: got in=%v out=%v", *p.InputPerMTok, *p.OutputPerMTok)
	}
	// Media dimensions stay nil — a text model is not priced for images etc.
	if p.PerImage != nil || p.PerSecond != nil || p.PerKChar != nil {
		t.Fatal("text model should not carry media pricing dimensions")
	}
}

func TestDefaultPricing_UnknownModel_FailsClosed(t *testing.T) {
	p, ok := DefaultPricing("openai", "gpt-9-imaginary")
	if ok {
		t.Fatal("unknown model must not be found in the default table")
	}
	// The zero Pricing has all-nil dimensions → the estimator fails closed.
	if p.InputPerMTok != nil || p.OutputPerMTok != nil {
		t.Fatal("unknown model must yield an empty (all-nil) Pricing")
	}
}

func TestDefaultPricing_ProviderKindIsPartOfKey(t *testing.T) {
	// A model name registered under the wrong provider_kind is unknown —
	// the key is the (provider_kind, model_name) pair.
	if _, ok := DefaultPricing("anthropic", "gpt-4o"); ok {
		t.Fatal("gpt-4o under provider_kind=anthropic must not match")
	}
	if _, ok := DefaultPricing("anthropic", "claude-opus-4"); !ok {
		t.Fatal("claude-opus-4 under provider_kind=anthropic should match")
	}
}
