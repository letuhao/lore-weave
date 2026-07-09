package billing

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func withOpenRouterURL(t *testing.T, url string) {
	t.Helper()
	orig := OpenRouterModelsURL
	OpenRouterModelsURL = url
	t.Cleanup(func() { OpenRouterModelsURL = orig })
}

func TestFetchOpenRouterPricing_FoundConvertsPerTokenToPerMTok(t *testing.T) {
	// Real live values captured 2026-07-09: gpt-4o's OpenRouter entry converts
	// to exactly this service's own hand-curated default (2.50/10.00) — the
	// unit-conversion (USD/token * 1e6 = USD/Mtok) this test locks in.
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"data":[
			{"id":"openai/gpt-4o","pricing":{"prompt":"0.0000025","completion":"0.00001"}},
			{"id":"openai/gpt-4o-mini","pricing":{"prompt":"0.00000015","completion":"0.0000006"}}
		]}`))
	}))
	defer ts.Close()
	withOpenRouterURL(t, ts.URL)

	got := FetchOpenRouterPricing(context.Background(), ts.Client(), "openai", "gpt-4o")
	if !got.Found {
		t.Fatalf("want Found=true, got %+v", got)
	}
	if got.SourceModelID != "openai/gpt-4o" {
		t.Errorf("want SourceModelID openai/gpt-4o, got %q", got.SourceModelID)
	}
	if got.Pricing == nil || got.Pricing.InputPerMTok == nil || got.Pricing.OutputPerMTok == nil {
		t.Fatalf("want non-nil pricing dims, got %+v", got.Pricing)
	}
	if *got.Pricing.InputPerMTok != 2.50 {
		t.Errorf("want input_per_mtok=2.50, got %v", *got.Pricing.InputPerMTok)
	}
	if *got.Pricing.OutputPerMTok != 10.00 {
		t.Errorf("want output_per_mtok=10.00, got %v", *got.Pricing.OutputPerMTok)
	}
}

func TestFetchOpenRouterPricing_GeminiMapsToGoogleNamespace(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"data":[{"id":"google/gemini-2.5-pro","pricing":{"prompt":"0.00000125","completion":"0.00001"}}]}`))
	}))
	defer ts.Close()
	withOpenRouterURL(t, ts.URL)

	got := FetchOpenRouterPricing(context.Background(), ts.Client(), "gemini", "gemini-2.5-pro")
	if !got.Found {
		t.Fatalf("want Found=true (gemini -> google namespace), got %+v", got)
	}
	if *got.Pricing.InputPerMTok != 1.25 {
		t.Errorf("want input_per_mtok=1.25, got %v", *got.Pricing.InputPerMTok)
	}
}

func TestFetchOpenRouterPricing_NoMatchingModelID(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"data":[{"id":"openai/gpt-4o","pricing":{"prompt":"0.0000025","completion":"0.00001"}}]}`))
	}))
	defer ts.Close()
	withOpenRouterURL(t, ts.URL)

	// A retired/renamed model absent from OpenRouter's CURRENT catalog (e.g. an
	// old Claude 3.5 naming OpenRouter no longer lists) — a real, expected,
	// non-error outcome, not a bug.
	got := FetchOpenRouterPricing(context.Background(), ts.Client(), "anthropic", "claude-3-5-sonnet")
	if got.Found {
		t.Fatalf("want Found=false for an unmatched model id, got %+v", got)
	}
}

func TestFetchOpenRouterPricing_UnmappedProviderKindNeverCallsNetwork(t *testing.T) {
	called := false
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		_, _ = w.Write([]byte(`{"data":[]}`))
	}))
	defer ts.Close()
	withOpenRouterURL(t, ts.URL)

	// lm_studio (a local BYOK kind) and any unrecognized cloud kind have no
	// OpenRouter mapping — this must short-circuit before any HTTP call.
	got := FetchOpenRouterPricing(context.Background(), ts.Client(), "lm_studio", "whatever")
	if got.Found {
		t.Fatalf("want Found=false for an unmapped provider_kind, got %+v", got)
	}
	if called {
		t.Fatal("want no network call for an unmapped provider_kind")
	}
}

func TestFetchOpenRouterPricing_NetworkErrorDegradesSafe(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer ts.Close()
	withOpenRouterURL(t, ts.URL)

	got := FetchOpenRouterPricing(context.Background(), ts.Client(), "openai", "gpt-4o")
	if got.Found {
		t.Fatalf("want Found=false on a non-200 upstream response, got %+v", got)
	}
}

func TestFetchOpenRouterPricing_MalformedBodyDegradesSafe(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`not json`))
	}))
	defer ts.Close()
	withOpenRouterURL(t, ts.URL)

	got := FetchOpenRouterPricing(context.Background(), ts.Client(), "openai", "gpt-4o")
	if got.Found {
		t.Fatalf("want Found=false on a malformed body, got %+v", got)
	}
}

func TestFetchOpenRouterPricing_NonNumericPriceStringDegradesSafe(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"data":[{"id":"openai/gpt-4o","pricing":{"prompt":"contact us","completion":"0.00001"}}]}`))
	}))
	defer ts.Close()
	withOpenRouterURL(t, ts.URL)

	got := FetchOpenRouterPricing(context.Background(), ts.Client(), "openai", "gpt-4o")
	if got.Found {
		t.Fatalf("want Found=false when a price field can't be parsed as a number, got %+v", got)
	}
}

func TestOpenRouterSuggestion_JSONShape(t *testing.T) {
	// Locks in the wire contract the FE reads: found/source_model_id/pricing.
	p := textPricing(2.5, 10.0)
	s := OpenRouterSuggestion{Found: true, SourceModelID: "openai/gpt-4o", Pricing: &p}
	b, err := json.Marshal(s)
	if err != nil {
		t.Fatal(err)
	}
	var round map[string]any
	if err := json.Unmarshal(b, &round); err != nil {
		t.Fatal(err)
	}
	if round["found"] != true || round["source_model_id"] != "openai/gpt-4o" {
		t.Errorf("unexpected round-trip: %v", round)
	}
	notFound := OpenRouterSuggestion{Found: false}
	b2, _ := json.Marshal(notFound)
	var round2 map[string]any
	_ = json.Unmarshal(b2, &round2)
	if _, has := round2["pricing"]; has {
		t.Errorf("want pricing omitted when not found, got %v", round2)
	}
	if _, has := round2["source_model_id"]; has {
		t.Errorf("want source_model_id omitted when not found, got %v", round2)
	}
}
