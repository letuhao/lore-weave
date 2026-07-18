package push

import (
	"fmt"
	"net"
	"net/url"
)

// ValidatePushEndpoint guards the register route against SSRF (cold-review HIGH-1). Without it, an
// authenticated user could register an endpoint pointing at an INTERNAL url (the cloud metadata IP,
// localhost, a sibling service) and then self-notify — making notification-service issue a
// server-side POST to that internal target, leaking status as an oracle (blind SSRF), and a
// slow/hung target would also pile up goroutines/FDs (DoS). A real browser push endpoint is always a
// PUBLIC https URL, so we require https and reject any host that resolves into a private / loopback /
// link-local range. (Allowlisting hosts is impossible — push services are many — but scheme + private
// -range rejection blocks every attack shape while accepting FCM/Mozilla/etc.)
//
// Residual (documented, follow-on): a host that resolves public at register but rebinds to a private
// IP at send time isn't caught here — that needs a dial-time check (a custom http client the webpush
// lib doesn't accept). The 30s send timeout (sender.go) bounds the damage window meanwhile.
func ValidatePushEndpoint(endpoint string) error {
	u, err := url.Parse(endpoint)
	if err != nil {
		return fmt.Errorf("invalid endpoint url")
	}
	if u.Scheme != "https" {
		return fmt.Errorf("endpoint must be https")
	}
	host := u.Hostname()
	if host == "" {
		return fmt.Errorf("endpoint has no host")
	}
	// An IP literal host: check it directly. A name: resolve + check every A/AAAA.
	if ip := net.ParseIP(host); ip != nil {
		if isDisallowedIP(ip) {
			return fmt.Errorf("endpoint address not allowed")
		}
		return nil
	}
	ips, err := net.LookupIP(host)
	if err != nil || len(ips) == 0 {
		return fmt.Errorf("endpoint host unresolvable")
	}
	for _, ip := range ips {
		if isDisallowedIP(ip) {
			return fmt.Errorf("endpoint resolves to a disallowed address")
		}
	}
	return nil
}

// isDisallowedIP rejects the address ranges an outbound push must never reach.
func isDisallowedIP(ip net.IP) bool {
	return ip.IsLoopback() || // 127.0.0.0/8, ::1
		ip.IsPrivate() || // RFC1918 + fc00::/7
		ip.IsLinkLocalUnicast() || // 169.254.0.0/16 (cloud metadata), fe80::/10
		ip.IsLinkLocalMulticast() ||
		ip.IsUnspecified() // 0.0.0.0, ::
}
