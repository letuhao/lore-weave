package tracing

// HeaderTraceparent is the W3C-spec header name. RFC 9110 declares HTTP
// header names case-insensitive; we use the lowercase canonical form.
const HeaderTraceparent = "traceparent"

// HeaderTracestate is the W3C-spec companion header for vendor extensions.
const HeaderTracestate = "tracestate"

// Headers is a minimal carrier interface implemented by both
// `http.Header` (via the stdlib http package) and the cycle-8 event
// envelope `Metadata map[string]string`. This package does NOT depend on
// net/http to keep the contract library dep-free; services bind via a
// trivial wrapper at the call site.
//
// Both Get and Set are case-INSENSITIVE per W3C (`traceparent` MUST be
// recognized regardless of case). The InMemoryHeaders impl below
// canonicalizes to lowercase.
type Headers interface {
	Get(key string) string
	Set(key, value string)
}

// MapHeaders is a map[string]string adapter that implements Headers.
// Used for the cycle-8 EventEnvelope.Metadata propagation surface.
// Keys are canonicalized to lowercase on Set.
type MapHeaders map[string]string

// Get returns the value for key (case-insensitive lookup).
func (m MapHeaders) Get(key string) string {
	if m == nil {
		return ""
	}
	if v, ok := m[lower(key)]; ok {
		return v
	}
	return m[key]
}

// Set assigns value to key (canonicalizes to lowercase).
func (m MapHeaders) Set(key, value string) {
	if m == nil {
		return
	}
	m[lower(key)] = value
}

func lower(s string) string {
	b := []byte(s)
	for i, c := range b {
		if c >= 'A' && c <= 'Z' {
			b[i] = c + ('a' - 'A')
		}
	}
	return string(b)
}

// Inject writes the W3C trace context into the carrier.
//
//   - traceparent is set to the FormatTraceparent(tc) value (or empty
//     string if tc.IsZero — defensive no-op so callers can pass a zero
//     context without crashing).
//   - tracestate is set to tc.State (which may be empty; we still call
//     Set with "" so the caller can detect "Inject was called").
//
// Returns false when tc.IsZero (no propagation performed).
func Inject(tc TraceContext, h Headers) bool {
	if h == nil {
		return false
	}
	if tc.IsZero() {
		return false
	}
	h.Set(HeaderTraceparent, FormatTraceparent(tc))
	h.Set(HeaderTracestate, tc.State)
	return true
}

// Extract reads the W3C trace context from the carrier.
//
// Returns (zero, false) when the traceparent header is missing or
// malformed. Caller can detect missing-vs-present via the bool.
func Extract(h Headers) (TraceContext, bool) {
	if h == nil {
		return TraceContext{}, false
	}
	raw := h.Get(HeaderTraceparent)
	if raw == "" {
		return TraceContext{}, false
	}
	tc, err := ParseTraceparent(raw)
	if err != nil {
		return TraceContext{}, false
	}
	tc.State = h.Get(HeaderTracestate)
	return tc, true
}
