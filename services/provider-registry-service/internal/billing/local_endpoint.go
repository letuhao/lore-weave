package billing

import (
	"encoding/json"
	"net"
	"net/url"
	"strings"
)

// IsLocalEndpoint reports whether a provider credential's base URL names an
// endpoint served from the operator's own machine or network — loopback, the
// Docker host alias, or an RFC-1918 address.
//
// 🔴 WHY THIS EXISTS. A model served from your own GPU costs no third party
// anything, but nothing stopped a local model from carrying a CLOUD price table.
// `google/gemma-4-26b-a4b-qat` sat at http://host.docker.internal:1234 with
// {"input_per_mtok":3.0,"output_per_mtok":15.0} and booked **$150.18 of spend in a
// single day** against a GPU in the next room. That is not merely a wrong report:
// spend_guardrails counts it, so a user who sets an HONEST daily cap gets locked
// out of hardware they own, by money they never spent.
//
// FAIL-SAFE DIRECTION. Unknown ⇒ REMOTE ⇒ billable. An empty or unparseable base
// URL (platform_models carry no credential at all) returns false, because the
// dangerous mistake in the other direction is silently under-reporting real spend.
// Only an endpoint we can positively identify as local goes free.
func IsLocalEndpoint(baseURL string) bool {
	s := strings.TrimSpace(baseURL)
	if s == "" {
		return false
	}
	// A bare "host:port" has no scheme; url.Parse would read "host" as the scheme.
	if !strings.Contains(s, "://") {
		s = "http://" + s
	}
	u, err := url.Parse(s)
	if err != nil {
		return false
	}
	h := strings.ToLower(strings.TrimSuffix(u.Hostname(), "."))
	if h == "" {
		return false
	}
	switch h {
	case "localhost",
		"host.docker.internal",     // Docker Desktop's alias for the host machine
		"gateway.docker.internal",  // …and its gateway
		"host.containers.internal", // the Podman equivalent
		"host.lima.internal":
		return true
	}
	if strings.HasSuffix(h, ".localhost") || strings.HasSuffix(h, ".local") ||
		strings.HasSuffix(h, ".internal") {
		return true
	}
	if ip := net.ParseIP(h); ip != nil {
		return ip.IsLoopback() || ip.IsPrivate() ||
			ip.IsLinkLocalUnicast() || ip.IsUnspecified()
	}
	return false
}

// FreePricing is an EXPLICITLY-ZERO price table: every dimension present and 0.
//
// 🔴 IT MUST NOT BE `Pricing{}`. An absent dimension is "unpriced", which the
// estimator fail-closes into a 402 (see ErrUnpriced) — so returning the zero VALUE
// here would take every local model offline rather than make it free. The pointer
// fields exist precisely to tell "absent" from "explicitly free"; this is the
// "explicitly free" case the Pricing doc comment names.
func FreePricing() Pricing {
	in, out, cached := 0.0, 0.0, 0.0
	img, sec, kchar := 0.0, 0.0, 0.0
	return Pricing{
		InputPerMTok:       &in,
		OutputPerMTok:      &out,
		CachedInputPerMTok: &cached,
		PerImage:           &img,
		PerSecond:          &sec,
		PerKChar:           &kchar,
	}
}

// DecodePricing turns a model's pricing JSONB into a Pricing, given the base URL
// of the credential that serves it.
//
// This is the ONE place a Pricing is produced for billing, and it takes the
// endpoint as a REQUIRED argument so that no future caller can price a model
// without first saying where that model runs. A local endpoint yields
// FreePricing regardless of what the JSONB claims — the stored price table of a
// local model is not evidence that anyone charged for it.
//
// Pass "" for a model with no credential (platform_models): unknown location is
// treated as remote, and the stored pricing applies.
func DecodePricing(raw []byte, endpointBaseURL string) (Pricing, error) {
	if IsLocalEndpoint(endpointBaseURL) {
		return FreePricing(), nil
	}
	var p Pricing
	if len(raw) == 0 {
		return p, nil
	}
	if err := json.Unmarshal(raw, &p); err != nil {
		return Pricing{}, err
	}
	return p, nil
}
