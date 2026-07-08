package api

// S5 LIVE-SMOKE — closes docs/specs/2026-07-07-mcp-discovery-and-reliability-hardening.md
// §1 Layer B ("web-search/deep-research reliability is genuinely unverified"): no existing
// test calls the REAL configured web-search provider and asserts real result content —
// web_search_test.go (adapter-level) and web_search_handler_integration_test.go (this
// package) always stub the upstream via httptest.Server, and
// server_websearch_verify_test.go's verifyWebSearch only pings connectivity
// (verified/result_count/reachable), never relevance. This test is the missing piece: it
// resolves whatever web_search-capable BYOK credential is ACTUALLY configured for a real
// user — through the service's own resolution path, internalWebSearch, exactly like a real
// caller — never a hardcoded URL/key, sends a real non-trivial query, and asserts non-empty,
// real-looking result content (real http(s) URLs + non-empty title/snippet text).
//
// Deliberately NOT part of default CI: requires TEST_PROVIDER_REGISTRY_DB_URL (like every
// other integration test in this package) AND an already-configured, active web_search
// user_model for the target owner — skips gracefully (not a failure) when either is
// missing, so this can never become a flaky CI-breaker. Run deliberately, e.g.:
//
//	TEST_PROVIDER_REGISTRY_DB_URL=postgres://loreweave:loreweave_dev@localhost:5555/loreweave_provider_registry?sslmode=disable \
//	  go test ./internal/api/ -run TestLive_WebSearch_RealProvider -v
//
// Optionally target a different account via LIVE_WEBSEARCH_OWNER_USER_ID (defaults to the
// dev test account documented in CLAUDE.md's "Test Account" section).

import (
	"encoding/json"
	"net/http"
	"os"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// defaultLiveWebSearchOwner is the repo's documented dev test account (CLAUDE.md "Test
// Account" — loreweave_auth.users.id for claude-test@loreweave.dev). It is NOT a
// provider URL or secret — just an owner_user_id used to look up whatever BYOK
// credential that account actually has configured, via the normal resolution query.
const defaultLiveWebSearchOwner = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"

func TestLive_WebSearch_RealProvider(t *testing.T) {
	srv, _ := integrationServer(t)

	ownerStr := os.Getenv("LIVE_WEBSEARCH_OWNER_USER_ID")
	if ownerStr == "" {
		ownerStr = defaultLiveWebSearchOwner
	}
	owner, err := uuid.Parse(ownerStr)
	if err != nil {
		t.Fatalf("LIVE_WEBSEARCH_OWNER_USER_ID (or default) is not a valid UUID: %v", err)
	}

	// A real, non-trivial query — the same shape as the 4-session repro in the spec
	// (a general, non-book-scoped web-search request), just in English for a
	// well-known, stable-ish topic so relevance is easy to eyeball from the assertions
	// below without pinning to today's news cycle.
	rr := callWebSearch(t, srv, owner, "latest news about the James Webb Space Telescope")

	if rr.Code == http.StatusNotFound {
		t.Skipf("no active web_search-capable BYOK provider configured for owner %s — "+
			"add a web-search provider credential (e.g. Tavily) in Settings for this account, "+
			"or set LIVE_WEBSEARCH_OWNER_USER_ID to an account that has one, to run this live "+
			"test (handler response: %s)", owner, rr.Body.String())
	}
	if rr.Code != http.StatusOK {
		t.Fatalf("live web search: want 200, got %d (%s) — this is a REAL Layer B failure, "+
			"not a config-missing skip", rr.Code, rr.Body.String())
	}

	var out struct {
		ProviderModel string `json:"provider_model"`
		Answer        string `json:"answer"`
		Results       []struct {
			Title   string  `json:"title"`
			URL     string  `json:"url"`
			Content string  `json:"content"`
			Score   float64 `json:"score"`
		} `json:"results"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode live response: %v (%s)", err, rr.Body.String())
	}

	if len(out.Results) == 0 {
		t.Fatalf("live web search returned ZERO results for a well-known, non-trivial query — "+
			"either the configured provider itself is broken/misconfigured or Layer B has a "+
			"real logic bug (full response: %s)", rr.Body.String())
	}

	realURLs, realText := 0, 0
	for i, res := range out.Results {
		url := strings.TrimSpace(res.URL)
		if url == "" {
			t.Errorf("result[%d] has an empty URL — not real content (%+v)", i, res)
		} else if strings.HasPrefix(url, "http://") || strings.HasPrefix(url, "https://") {
			realURLs++
		} else {
			t.Errorf("result[%d].URL %q does not look like a real URL", i, res.URL)
		}
		if strings.TrimSpace(res.Title) != "" || strings.TrimSpace(res.Content) != "" {
			realText++
		}
	}
	if realURLs == 0 {
		t.Fatalf("no result carried a real http(s) URL — provider returned junk: %+v", out.Results)
	}
	if realText == 0 {
		t.Fatalf("no result carried a non-empty title or snippet — provider returned junk: %+v", out.Results)
	}

	t.Logf("LIVE-SMOKE web search OK: provider_model=%q results=%d answer_len=%d first_url=%q first_title=%q",
		out.ProviderModel, len(out.Results), len(out.Answer), out.Results[0].URL, out.Results[0].Title)
}
