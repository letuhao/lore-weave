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

func TestDefaultPricing_LocalProviderKinds_FreeAcrossAllDimensions(t *testing.T) {
	// Self-hosted providers run on the user's own compute → priced-free (every
	// dimension explicit 0, NOT nil), so a local model never 402s regardless of
	// operation (chat/tts/stt/image_gen/embedding). Regression-locks the
	// TR-4-adjacent fix (2026-05-31): local TTS/LLM models were failing closed.
	for _, kind := range []string{"lm_studio", "ollama", "kokoro_local", "whisper_local"} {
		p, ok := DefaultPricing(kind, "any-local-model")
		if !ok {
			t.Fatalf("%s: local provider must pre-fill pricing (found=false)", kind)
		}
		dims := map[string]*float64{
			"input": p.InputPerMTok, "output": p.OutputPerMTok,
			"image": p.PerImage, "second": p.PerSecond, "kchar": p.PerKChar,
		}
		for name, v := range dims {
			if v == nil {
				t.Fatalf("%s: dimension %q must be non-nil (priced-free), got nil (unpriced→402)", kind, name)
			}
			if *v != 0 {
				t.Fatalf("%s: dimension %q must be 0, got %v", kind, name, *v)
			}
		}
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
