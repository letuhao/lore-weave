package billing

import (
	"errors"
	"testing"
)

// C6 / SD-C6 — PriceSTT (per audio-second) + PriceTTS (per 1000 chars) resolve from the model's rate.
func TestPriceSTT_PerSecond(t *testing.T) {
	rate := 0.006 // $0.006 / audio-second (~$0.36/min, Whisper-cloud-ish)
	p := Pricing{PerSecond: &rate}
	usd, err := PriceSTT(120, p) // 2 minutes = 120s → 120 × 0.006 = 0.72 (EXACT — catches a 60× error)
	if err != nil {
		t.Fatal(err)
	}
	if usd != 0.72 {
		t.Fatalf("STT 120s × $0.006/s must be EXACTLY $0.72, got %v (a per-minute-vs-per-second mixup?)", usd)
	}
	// unpriced model (no per_second) fails closed
	if _, err := PriceSTT(120, Pricing{}); !errors.Is(err, ErrUnpriced) {
		t.Fatalf("an unpriced STT model must be ErrUnpriced, got %v", err)
	}
	// an explicit $0 local model prices to 0 (not unpriced)
	zero := 0.0
	if usd, err := PriceSTT(120, Pricing{PerSecond: &zero}); err != nil || usd != 0 {
		t.Fatalf("a $0 local STT model must price to 0, got %v %v", usd, err)
	}
}

func TestPriceTTS_PerKChar(t *testing.T) {
	rate := 15.0 // $15 / 1k chars (a deliberately round rate for an exact assertion)
	p := Pricing{PerKChar: &rate}
	usd, err := PriceTTS(2000, p) // 2000 chars = 2 kchar → 2 × 15 = 30.0 (EXACT)
	if err != nil {
		t.Fatal(err)
	}
	if usd != 30.0 {
		t.Fatalf("TTS 2000 chars × $15/kchar must be EXACTLY $30.00, got %v", usd)
	}
	if _, err := PriceTTS(2000, Pricing{}); !errors.Is(err, ErrUnpriced) {
		t.Fatalf("an unpriced TTS model must be ErrUnpriced, got %v", err)
	}
	zero := 0.0
	if usd, err := PriceTTS(2000, Pricing{PerKChar: &zero}); err != nil || usd != 0 {
		t.Fatalf("a $0 local TTS model must price to 0, got %v %v", usd, err)
	}
	// negative chars clamp to 0
	if usd, _ := PriceTTS(-5, Pricing{PerKChar: &rate}); usd != 0 {
		t.Fatalf("negative chars must clamp to 0 cost, got %v", usd)
	}
}
