package billing

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// withOpenRouterURL points the fetch at a test server AND resets the
// in-memory catalog cache (both before the test body and after cleanup) — the
// /review-impl MED#1 caching fix means a prior test's mock response would
// otherwise leak into a later test via the shared package-level cache instead
// of hitting that test's own httptest.Server.
func withOpenRouterURL(t *testing.T, url string) {
	t.Helper()
	orig := OpenRouterModelsURL
	OpenRouterModelsURL = url
	openRouterCache = openRouterCacheState{}
	t.Cleanup(func() {
		OpenRouterModelsURL = orig
		openRouterCache = openRouterCacheState{}
	})
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

// /review-impl MED#1 (2026-07-09): every "Check OpenRouter" click used to
// re-fetch the ENTIRE catalog uncached — this proves the fix: a second call
// within the TTL must NOT hit the network again.
func TestFetchOpenRouterPricing_CachesAndAvoidsRepeatFetch(t *testing.T) {
	calls := 0
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		_, _ = w.Write([]byte(`{"data":[{"id":"openai/gpt-4o","pricing":{"prompt":"0.0000025","completion":"0.00001"}}]}`))
	}))
	defer ts.Close()
	withOpenRouterURL(t, ts.URL)

	first := FetchOpenRouterPricing(context.Background(), ts.Client(), "openai", "gpt-4o")
	second := FetchOpenRouterPricing(context.Background(), ts.Client(), "openai", "gpt-4o-mini")
	if !first.Found {
		t.Fatalf("want first call found, got %+v", first)
	}
	if calls != 1 {
		t.Fatalf("want exactly 1 network call across 2 lookups within the TTL, got %d", calls)
	}
	// gpt-4o-mini isn't in this mock's catalog, but the cache was still reused
	// (not a bug — just proves the SAME cached list served both lookups).
	if second.Found {
		t.Fatalf("want second lookup (absent from the mock catalog) to be not-found, got %+v", second)
	}
}

// /review-impl MED#1: on a fetch failure, a previously-populated cache should
// still serve (better than losing the feature over a transient hiccup) —
// this must never surface as an error to the caller either way.
func TestFetchOpenRouterPricing_ServesStaleCacheOnLaterFetchError(t *testing.T) {
	failing := false
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if failing {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		_, _ = w.Write([]byte(`{"data":[{"id":"openai/gpt-4o","pricing":{"prompt":"0.0000025","completion":"0.00001"}}]}`))
	}))
	defer ts.Close()
	withOpenRouterURL(t, ts.URL)

	warm := FetchOpenRouterPricing(context.Background(), ts.Client(), "openai", "gpt-4o")
	if !warm.Found {
		t.Fatalf("want the warm-up call found, got %+v", warm)
	}

	failing = true
	// Force a re-fetch attempt (bypassing the fresh-cache short-circuit) by
	// expiring the cache directly — the TTL is 10 minutes, too long to wait in
	// a unit test, and this test is specifically about the fetch-failure path.
	openRouterCache.fetchedAt = openRouterCache.fetchedAt.Add(-2 * openRouterCacheTTL)

	stale := FetchOpenRouterPricing(context.Background(), ts.Client(), "openai", "gpt-4o")
	if !stale.Found {
		t.Fatalf("want the stale cache to still serve found=true despite the upstream 500, got %+v", stale)
	}
}

// /review-impl LOW#3 (2026-07-09): openRouterNamespace and defaultPriceTable
// are two independently hand-maintained provider_kind lists with nothing else
// tying them together. A future cloud provider_kind added to defaultPriceTable
// without a matching openRouterNamespace entry would silently make "Check
// OpenRouter" always return not-found for every model of that kind — this
// test is the drift-catcher.
func TestOpenRouterNamespace_CoversEveryDefaultPricingProviderKind(t *testing.T) {
	seen := map[string]bool{}
	for key := range defaultPriceTable {
		kind, _, ok := strings.Cut(key, "\x00")
		if !ok {
			t.Fatalf("malformed defaultPriceTable key %q (expected providerKind\\x00modelName)", key)
		}
		seen[kind] = true
	}
	if len(seen) == 0 {
		t.Fatal("defaultPriceTable is empty — this test can't prove anything; update it if the table was intentionally cleared")
	}
	for kind := range seen {
		if _, ok := openRouterNamespace[kind]; !ok {
			t.Errorf("provider_kind %q is priced in defaultPriceTable but has no openRouterNamespace mapping — "+
				"the Check-OpenRouter suggestion button will silently always say \"not found\" for every model of this kind", kind)
		}
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
