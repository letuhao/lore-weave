package billing

import (
	"errors"
	"testing"
)

// gemmaPricingJSONB is the EXACT pricing column of user_model
// 019ebb72-27a2-72f3-a42d-d2d0e0ded179 (google/gemma-4-26b-a4b-qat), read from
// loreweave_provider_registry on 2026-09-01.
const gemmaPricingJSONB = `{"per_image":0,"per_kchar":0,"per_second":0,"input_per_mtok":3.0,"output_per_mtok":15.0}`

// gemmaEndpoint is that model's credential base URL — LM Studio on the host GPU.
const gemmaEndpoint = "http://host.docker.internal:1234"

// One real hour of that model's traffic, from usage_logs on 2026-09-01 09:00Z.
const (
	gemmaHourInputTokens  = 10832604
	gemmaHourOutputTokens = 52358
)

// 🔴 THE ORIGINAL INSTANCE. Priced as stored, this single hour bills $32.28 and the
// full day billed $150.18 — for a model running on a GPU in the next room. The bug is
// not cosmetic: spend_guardrails.daily_spent_usd counted every cent of it, so an
// operator who sets an honest cap is locked out of their own hardware.
func TestALocalModelIsNeverBilled(t *testing.T) {
	p, err := DecodePricing([]byte(gemmaPricingJSONB), gemmaEndpoint)
	if err != nil {
		t.Fatalf("DecodePricing: %v", err)
	}
	got, err := PriceText(gemmaHourInputTokens, gemmaHourOutputTokens, p)
	if err != nil {
		t.Fatalf("PriceText: %v", err)
	}
	if got != 0 {
		t.Errorf("one hour on the LOCAL GPU billed $%.2f, want $0.00 — a model served "+
			"from %s costs no third party anything, whatever its stored price table says",
			got, gemmaEndpoint)
	}
}

// 🔴 THE OBVIOUS FIX IS A WORSE BUG. Returning an EMPTY Pricing for a local model
// would read as "unpriced", which the estimator fail-closes into a 402 — taking every
// local model OFFLINE instead of making it free. Free must be EXPLICIT zeros.
func TestALocalModelIsFreeNotUnpriced(t *testing.T) {
	p, err := DecodePricing(nil, gemmaEndpoint)
	if err != nil {
		t.Fatalf("DecodePricing: %v", err)
	}
	if _, err := PriceText(1000, 1000, p); err != nil {
		if errors.Is(err, ErrUnpriced) {
			t.Fatal("a local model came back UNPRICED — every local call now fail-closes " +
				"with a 402 and the user's own GPU is unreachable")
		}
		t.Fatalf("PriceText: %v", err)
	}
	if _, err := PriceEmbedding(1000, p); err != nil {
		t.Errorf("local embedding unpriced: %v", err)
	}
	if _, err := PriceTTS(1000, p); err != nil {
		t.Errorf("local TTS unpriced: %v", err)
	}
	if _, err := PriceSTT(60, p); err != nil {
		t.Errorf("local STT unpriced: %v", err)
	}
}

// 🔴 THE TEETH AGAINST AN OVER-BROAD FIX. glm-5.3-flash is a real paid endpoint on the
// same provider KIND ("ollama") as the local one. A fix keyed on provider_kind rather
// than on the endpoint would zero this too and hide genuine spend.
func TestARemoteModelOnTheSameProviderKindKeepsItsPrice(t *testing.T) {
	const glmPricing = `{"input_per_mtok":0.15,"output_per_mtok":0.50,"cached_input_per_mtok":0.03}`
	p, err := DecodePricing([]byte(glmPricing), "https://ollama.com")
	if err != nil {
		t.Fatalf("DecodePricing: %v", err)
	}
	got, err := PriceText(1_000_000, 0, p)
	if err != nil {
		t.Fatalf("PriceText: %v", err)
	}
	if got != 0.15 {
		t.Errorf("remote glm-5.3-flash billed $%.4f for 1M input tokens, want $0.1500 — "+
			"zeroing by provider_kind would make real cloud spend invisible", got)
	}
}

// An absent endpoint (platform_models carry no credential) must bill. Under-reporting
// real spend is the dangerous direction; over-reporting is merely wrong.
func TestAnUnknownEndpointIsTreatedAsRemote(t *testing.T) {
	p, err := DecodePricing([]byte(gemmaPricingJSONB), "")
	if err != nil {
		t.Fatalf("DecodePricing: %v", err)
	}
	got, err := PriceText(1_000_000, 0, p)
	if err != nil {
		t.Fatalf("PriceText: %v", err)
	}
	if got == 0 {
		t.Error("an endpoint we cannot place was billed $0 — unknown must fail SAFE " +
			"(billable), or real spend disappears from the guardrail")
	}
}

func TestIsLocalEndpoint(t *testing.T) {
	local := []string{
		"http://host.docker.internal:1234/v1", // every lm_studio credential in this deployment
		"http://host.docker.internal:11434",   // local ollama
		"http://127.0.0.1:28417",
		"http://localhost:15487",
		"https://[::1]:8080",
		"http://192.168.1.50:1234", // a LAN box is still the operator's own hardware
		"http://10.0.0.7:11434",
		"http://172.16.4.4:11434",
		"host.docker.internal:1234", // no scheme — must not parse "host" as one
		"http://my-rig.local:1234",
	}
	for _, u := range local {
		if !IsLocalEndpoint(u) {
			t.Errorf("IsLocalEndpoint(%q) = false, want true — this endpoint bills for "+
				"hardware the operator already owns", u)
		}
	}
	remote := []string{
		"https://ollama.com",
		"https://api.openai.com/v1",
		"https://api.anthropic.com",
		"", // no credential → unknown → billable
		"://://",
		"http://1.2.3.4:11434",
		// A public host whose NAME merely contains a local-looking token.
		"https://localhost.example.com",
		"https://internal.example.com",
	}
	for _, u := range remote {
		if IsLocalEndpoint(u) {
			t.Errorf("IsLocalEndpoint(%q) = true, want false — real spend would vanish", u)
		}
	}
}
