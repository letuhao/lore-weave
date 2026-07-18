package api

// glossary_web_search — S5 LIVE-SMOKE (glossary-service half). Closes
// docs/specs/2026-07-07-mcp-discovery-and-reliability-hardening.md §1 Layer B
// ("web-search/deep-research reliability is genuinely unverified") for THIS service's
// half of the round trip: web_search_tool_test.go only ever calls toolWebSearch against
// an httptest.Server stub standing in for provider-registry — no test anywhere exercises
// glossary's actual webSearch() HTTP client against a REAL, RUNNING provider-registry-service,
// so a break in that hop (wrong internal-token, wrong response shape, a real provider outage)
// would never be caught by the existing suite. provider-registry-service's own
// web_search_live_test.go (TestLive_WebSearch_RealProvider) already closes the OTHER half
// (provider-registry → the actual upstream search provider); this test closes the
// glossary → provider-registry hop, end to end, with no stub in the middle.
//
// Deliberately NOT part of default CI / `go test ./...`: requires a RUNNING
// provider-registry-service reachable at GLOSSARY_LIVE_PROVIDER_REGISTRY_URL, tagged with
// GLOSSARY_LIVE_INTERNAL_TOKEN matching that instance's INTERNAL_SERVICE_TOKEN, AND an
// already-configured, active web_search-capable BYOK credential for the target owner —
// skips gracefully (never a failure) when any of these is missing, so it can never become a
// flaky CI-breaker. Run deliberately, e.g. (dev-compose default ports):
//
//	GLOSSARY_LIVE_PROVIDER_REGISTRY_URL=http://localhost:8087 \
//	GLOSSARY_LIVE_INTERNAL_TOKEN=dev_internal_token \
//	  go test ./internal/api/ -run TestLive_GlossaryWebSearch_RealProvider -v
//
// Optionally target a different account via LIVE_WEBSEARCH_OWNER_USER_ID (same env var
// provider-registry-service's own live-smoke test reads; defaults to the repo's documented
// dev test account — CLAUDE.md "Test Account").

import (
	"os"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// glossaryLiveWebSearchOwner is the repo's documented dev test account (CLAUDE.md "Test
// Account" — loreweave_auth.users.id for claude-test@loreweave.dev). It is NOT a provider
// URL or secret — just an owner_user_id used to resolve whatever BYOK web_search credential
// that account actually has configured, via provider-registry's normal resolution path.
const glossaryLiveWebSearchOwner = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"

func TestLive_GlossaryWebSearch_RealProvider(t *testing.T) {
	baseURL := strings.TrimSpace(os.Getenv("GLOSSARY_LIVE_PROVIDER_REGISTRY_URL"))
	if baseURL == "" {
		t.Skip("GLOSSARY_LIVE_PROVIDER_REGISTRY_URL not set — skipping live glossary_web_search " +
			"smoke (set it to a RUNNING provider-registry-service URL, e.g. http://localhost:8087, " +
			"to run this test)")
	}
	token := strings.TrimSpace(os.Getenv("GLOSSARY_LIVE_INTERNAL_TOKEN"))
	if token == "" {
		t.Skip("GLOSSARY_LIVE_INTERNAL_TOKEN not set — skipping live glossary_web_search smoke " +
			"(set it to that provider-registry-service instance's INTERNAL_SERVICE_TOKEN)")
	}

	ownerStr := os.Getenv("LIVE_WEBSEARCH_OWNER_USER_ID")
	if ownerStr == "" {
		ownerStr = glossaryLiveWebSearchOwner
	}
	owner, err := uuid.Parse(ownerStr)
	if err != nil {
		t.Fatalf("LIVE_WEBSEARCH_OWNER_USER_ID (or the default) is not a valid UUID: %v", err)
	}

	srv := newWebSearchServer(t, baseURL)
	srv.cfg.InternalServiceToken = token

	// A real, non-trivial, non-book-scoped query — the same shape as the 4-session repro in
	// the spec (a general web-search request with no book context).
	_, out, err := srv.toolWebSearch(ctxWithUser(owner), nil,
		webSearchToolIn{Query: "latest news about the James Webb Space Telescope", MaxResults: 5})
	if err != nil {
		if strings.Contains(err.Error(), "not configured") {
			t.Skipf("owner %s has no active web_search-capable BYOK credential configured — add "+
				"one (e.g. Tavily) in Settings for this account, or set LIVE_WEBSEARCH_OWNER_USER_ID "+
				"to an account that has one, to run this live test (%v)", owner, err)
		}
		t.Fatalf("live glossary_web_search call failed: %v — this is a REAL Layer B failure "+
			"(a genuine glossary→provider-registry wiring or provider bug), not a config-missing skip", err)
	}

	if len(out.Sources) == 0 {
		t.Fatalf("live glossary_web_search returned ZERO sources for a well-known, non-trivial "+
			"query — either the configured provider itself is broken/misconfigured or this service's "+
			"webSearch() hop has a real bug (full output: %+v)", out)
	}

	realURLs, realText := 0, 0
	for i, src := range out.Sources {
		u := strings.TrimSpace(src.URL)
		switch {
		case u == "":
			t.Errorf("source[%d] has an empty URL — not real content (%+v)", i, src)
		case strings.HasPrefix(u, "http://") || strings.HasPrefix(u, "https://"):
			realURLs++
		default:
			t.Errorf("source[%d].URL %q does not look like a real http(s) URL", i, src.URL)
		}
		if strings.TrimSpace(src.Title) != "" || strings.TrimSpace(src.Snippet) != "" {
			realText++
		}
	}
	if realURLs == 0 {
		t.Fatalf("no source carried a real http(s) URL — provider returned junk: %+v", out.Sources)
	}
	if realText == 0 {
		t.Fatalf("no source carried a non-empty title or snippet — provider returned junk: %+v", out.Sources)
	}

	t.Logf("LIVE-SMOKE glossary_web_search OK: sources=%d answer_len=%d first_url=%q first_title=%q",
		len(out.Sources), len(out.Answer), out.Sources[0].URL, out.Sources[0].Title)
}
