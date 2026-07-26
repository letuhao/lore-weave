package provider

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"unicode"
)

// WebSearchResult is one ranked web result from a BYOK web-search provider.
type WebSearchResult struct {
	Title   string  `json:"title"`
	URL     string  `json:"url"`
	Content string  `json:"content"`
	Score   float64 `json:"score"`
}

// INV-6 neutralization caps (Track D S-PRODUCER). Web-search results are UNTRUSTED
// external text; these caps + neutralizeWebText + safeHTTPURL are the SINGLE producer
// chokepoint every consumer inherits — no consumer neutralizes again. The caps are the
// union of the (drifted) consumer copies that previously triplicated this: composition's
// web_search_client.py and glossary's pipeline_deep_research.go both used 200/600/1200,
// so the union is those values (glossary caps by byte length; we keep that stricter form).
const (
	webSearchTitleCap   = 200  // bytes per result title
	webSearchSnippetCap = 600  // bytes per result content/snippet
	webSearchAnswerCap  = 1200 // bytes for the provider's synthesized answer
	webSearchURLCap     = 2048 // a real URL is well under this
)

// neutralizeWebText makes untrusted fetched web text safe to return as quoted DATA
// (INV-6). It is the UNION of the two prior consumer implementations, taking the
// strictest of each:
//   - drops ALL Unicode control chars (glossary's unicode.IsControl — stricter than the
//     Python copy which only stripped \x00-\x1f\x7f and let C1 controls U+0080-U+009F pass);
//   - folds every Unicode whitespace/separator (incl. line/paragraph separators U+2028/9,
//     NBSP, \n \t \r) to a single space and collapses runs (so layout/line tricks can't
//     fake a chat turn or hidden structure — union of Python's `\s+` collapse and
//     glossary's `\n\t\r`→space);
//   - hard-caps by BYTE length (glossary's byte cap — stricter than Python's rune cap for
//     multibyte text), never splitting a rune.
//
// It does NOT try to "understand" the text — the consumer always frames it as DATA.
func neutralizeWebText(sval string, maxLen int) string {
	var b strings.Builder
	lastSpace := false
	for _, r := range sval {
		// Control chars and any whitespace/separator → a single inert space. Converting
		// (rather than dropping) preserves word boundaries so "ignore\x00previous" can't
		// collapse into one token.
		if unicode.IsControl(r) || unicode.IsSpace(r) {
			r = ' '
		}
		if r == ' ' {
			if lastSpace {
				continue
			}
			lastSpace = true
		} else {
			lastSpace = false
		}
		b.WriteRune(r)
		if b.Len() >= maxLen {
			break
		}
	}
	return strings.TrimSpace(b.String())
}

// safeHTTPURL accepts only http(s) URLs with a host, rejecting everything else so a
// hostile search result cannot smuggle a dangerous scheme (javascript:/data:/file:) OR an
// SSRF target to any downstream consumer that might fetch or render the URL. It is the
// UNION of the prior copies PLUS the SSRF block that NEITHER previously had (the headline
// drift finding): composition only regex-matched `^https?://` (no host/SSRF check) and
// glossary parsed scheme+host but ALSO let internal targets through. This producer now
// additionally drops loopback / link-local (incl. the 169.254.169.254 cloud-metadata IP) /
// private / unspecified hosts and the `localhost`/`*.local`/`*.internal` names.
//
// NOTE: the producer returns URLs as DATA and never fetches them, so redirect-to-internal
// SSRF (a public host that 30x-redirects to an internal one) cannot be detected here; a
// consumer that actually fetches a returned URL must re-validate after each redirect hop.
func safeHTTPURL(raw string) (string, bool) {
	raw = strings.TrimSpace(raw)
	if raw == "" || len(raw) > webSearchURLCap {
		return "", false
	}
	u, err := url.Parse(raw)
	if err != nil {
		return "", false
	}
	if (u.Scheme != "http" && u.Scheme != "https") || u.Hostname() == "" {
		return "", false
	}
	if isInternalHost(u.Hostname()) {
		return "", false
	}
	return u.String(), true
}

// isInternalHost reports whether a URL host targets the local machine or a private network
// — an SSRF-y destination that must never be handed onward. Literal IPs are classified via
// net.IP (loopback 127/8 + ::1, link-local 169.254/16 + fe80::/10 incl. the AWS/GCP
// 169.254.169.254 metadata endpoint, private 10/172.16/192.168 + fc00::/7, unspecified
// 0.0.0.0 + ::); hostnames block `localhost` and the conventional internal suffixes. It
// does NOT resolve DNS (neutralization must stay offline/synchronous) — a public hostname
// that resolves to an internal IP is out of scope here, same caveat as redirect-to-internal.
func isInternalHost(host string) bool {
	h := strings.ToLower(strings.TrimSuffix(host, "."))
	if h == "localhost" || strings.HasSuffix(h, ".localhost") ||
		strings.HasSuffix(h, ".local") || strings.HasSuffix(h, ".internal") {
		return true
	}
	if ip := net.ParseIP(h); ip != nil {
		return ip.IsLoopback() || ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() ||
			ip.IsPrivate() || ip.IsUnspecified() || ip.IsMulticast()
	}
	// net.ParseIP only accepts canonical dotted-quad / colon IPs, so it MISSES the
	// classic SSRF-obfuscation encodings that libc / browsers / curl / python-requests
	// still dereference to the same address: a bare integer (http://2130706433/ == 127.0.0.1,
	// http://2852039166/ == 169.254.169.254), hex (0x7f000001), octal (017700000001), and the
	// short dotted form (127.1 → 127.0.0.1). We return URLs as DATA, but a non-Go downstream
	// fetcher would resolve these — so treat any host that isn't a real DNS name (a real
	// hostname always has a non-numeric label, i.e. an alpha TLD) as an obfuscated address.
	return isObfuscatedNumericHost(h)
}

// isObfuscatedNumericHost reports whether a host that net.ParseIP already REJECTED is
// nonetheless a numeric IP in disguise. A legitimate DNS hostname always carries at least
// one label with a non-hex-digit character (the alphabetic TLD), so:
//   - a bare token that strconv can parse as an integer in ANY base (decimal / 0x-hex /
//     0-octal) is an obfuscated IP; and
//   - a dotted host whose every label is purely DECIMAL is a short/overflowed IP form
//     (127.1, 0.0.0.0.0, 999.999...) that ParseIP declined but a resolver may still expand.
//
// Decimal-only for the dotted case deliberately avoids flagging real hex-lookalike domains
// like "cafe.babe" (labels contain a-f but are legitimate DNS names).
func isObfuscatedNumericHost(h string) bool {
	if h == "" || strings.Contains(h, ":") {
		return false // v6 already handled by ParseIP above
	}
	if !strings.Contains(h, ".") {
		// base 0 = auto-detect: "0x.." hex, "0.." octal, otherwise decimal.
		_, err := strconv.ParseUint(h, 0, 64)
		return err == nil
	}
	for _, label := range strings.Split(h, ".") {
		if label == "" {
			return false
		}
		for _, r := range label {
			if r < '0' || r > '9' {
				return false // a non-decimal label ⇒ a genuine hostname
			}
		}
	}
	return true // every label was purely decimal ⇒ a short/obfuscated dotted IP
}

// WebSearchOptions tunes a search call.
type WebSearchOptions struct {
	MaxResults  int    // clamped to 1..20 (default 5)
	SearchDepth string // "basic" (default) | "advanced"
}

// WebSearch runs a web search via a Tavily-compatible API (POST {base}/search).
// Like Rerank it receives a RESOLVED endpointBaseURL + secret (BYOK) — no SDK, no
// config. This is the ONLY place the outward web-search HTTP call lives
// (provider-gateway invariant). Returns the ranked results + the provider's optional
// synthesized answer. The result `Content` is UNTRUSTED external text — the caller
// MUST neutralize it before it touches a prompt or lands as evidence (INV-6 / S24).
func WebSearch(ctx context.Context, client *http.Client, endpointBaseURL, secret, query string, opts WebSearchOptions) ([]WebSearchResult, string, error) {
	base := strings.TrimRight(endpointBaseURL, "/")
	if base == "" {
		base = "https://api.tavily.com"
	}
	// Tolerate a base stored with a trailing /search so we don't post to /search/search.
	base = strings.TrimSuffix(base, "/search")

	maxResults := opts.MaxResults
	if maxResults <= 0 || maxResults > 20 {
		maxResults = 5
	}
	depth := opts.SearchDepth
	if depth != "advanced" {
		depth = "basic"
	}

	headers := map[string]string{}
	if secret != "" {
		// Modern Tavily accepts a Bearer token; the api_key body field below keeps
		// older / self-hosted Tavily-compatible endpoints working too.
		headers["Authorization"] = "Bearer " + secret
	}
	payload := map[string]any{
		"api_key":        secret,
		"query":          query,
		"max_results":    maxResults,
		"search_depth":   depth,
		"include_answer": true,
	}
	out, err := postJSON(ctx, client, base+"/search", headers, payload)
	if err != nil {
		return nil, "", fmt.Errorf("web search call failed: %w", err)
	}
	answer, _ := out["answer"].(string)
	raw, _ := out["results"].([]any)
	results := make([]WebSearchResult, 0, len(raw))
	for _, item := range raw {
		entry, ok := item.(map[string]any)
		if !ok {
			continue
		}
		// INV-6 producer neutralization (fail-closed): an unsafe/SSRF-y URL drops the
		// WHOLE result — we never emit a hit a consumer could follow to an internal
		// target or render as javascript:/data:. Title/content are folded to inert,
		// length-capped single-line DATA.
		safeURL, ok := safeHTTPURL(wsString(entry["url"]))
		if !ok {
			continue
		}
		results = append(results, WebSearchResult{
			Title:   neutralizeWebText(wsString(entry["title"]), webSearchTitleCap),
			URL:     safeURL,
			Content: neutralizeWebText(wsString(entry["content"]), webSearchSnippetCap),
			Score:   toFloat(entry["score"]),
		})
	}
	return results, neutralizeWebText(answer, webSearchAnswerCap), nil
}

func wsString(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}
