package tracing

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"regexp"
)

// TraceContext is the typed view of W3C Trace Context propagated across
// service boundaries.
//
// Wire format ("traceparent" header):
//
//	"00-<32-hex-trace-id>-<16-hex-parent-id>-<2-hex-flags>"  (55 chars)
//
// version is pinned to 0x00 (cycle 32 + W3C V1). Any other version is
// rejected by ParseTraceparent.
type TraceContext struct {
	// TraceID is the 128-bit trace identifier (16 bytes). Stable across
	// every span in the request flow.
	TraceID [16]byte

	// SpanID is the 64-bit identifier of the CURRENT span (the parent_id
	// when this context is propagated to a downstream service — the
	// downstream service generates its own SpanID for its work).
	SpanID [8]byte

	// Flags is the W3C flags byte. Bit 0 (0x01) = sampled.
	Flags byte

	// State is the W3C `tracestate` header value — opaque key=value
	// list (max 512 chars per W3C). Foundation does NOT parse it; just
	// passes through.
	State string
}

// Sampled returns true when the sampled-bit (0x01) is set in Flags.
func (tc TraceContext) Sampled() bool { return tc.Flags&0x01 == 0x01 }

// IsZero returns true when no trace context is active (both IDs are zero).
func (tc TraceContext) IsZero() bool {
	for _, b := range tc.TraceID {
		if b != 0 {
			return false
		}
	}
	for _, b := range tc.SpanID {
		if b != 0 {
			return false
		}
	}
	return true
}

// TraceIDHex returns the 32-char lowercase hex form of TraceID.
func (tc TraceContext) TraceIDHex() string { return hex.EncodeToString(tc.TraceID[:]) }

// SpanIDHex returns the 16-char lowercase hex form of SpanID.
func (tc TraceContext) SpanIDHex() string { return hex.EncodeToString(tc.SpanID[:]) }

// FormatTraceparent serializes tc into the 55-char W3C `traceparent` value.
// Returns "" for a zero context (caller MUST check IsZero first).
func FormatTraceparent(tc TraceContext) string {
	if tc.IsZero() {
		return ""
	}
	return fmt.Sprintf("00-%s-%s-%02x", tc.TraceIDHex(), tc.SpanIDHex(), tc.Flags)
}

// traceparentRegex is the strict W3C V1 validator. Pinned to version=00.
// Total length 55 chars; lowercase hex required.
var traceparentRegex = regexp.MustCompile(`^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$`)

// ErrInvalidTraceparent is returned by ParseTraceparent on malformed input.
var ErrInvalidTraceparent = errors.New("tracing: invalid W3C traceparent (must be 55-char 00-<32hex>-<16hex>-<2hex>)")

// ErrZeroTraceID is returned when the parsed trace_id is all zeros (W3C
// disallows zero trace_id — defense vs noisy probes).
var ErrZeroTraceID = errors.New("tracing: trace_id must not be all zeros")

// ErrZeroSpanID is returned when the parsed span_id is all zeros.
var ErrZeroSpanID = errors.New("tracing: parent_id must not be all zeros")

// ParseTraceparent parses a 55-char W3C `traceparent` header value into a
// typed TraceContext. Strict validation:
//
//   - Version byte must be 0x00 (we don't support W3C V2+)
//   - Hex must be lowercase (W3C: "lowercase hex characters")
//   - Trace ID and Span ID must not be all-zeros
func ParseTraceparent(s string) (TraceContext, error) {
	if len(s) != 55 {
		return TraceContext{}, fmt.Errorf("%w: length=%d", ErrInvalidTraceparent, len(s))
	}
	m := traceparentRegex.FindStringSubmatch(s)
	if m == nil {
		return TraceContext{}, fmt.Errorf("%w: format mismatch", ErrInvalidTraceparent)
	}
	tcid, err := hex.DecodeString(m[1])
	if err != nil {
		return TraceContext{}, fmt.Errorf("%w: trace_id hex: %v", ErrInvalidTraceparent, err)
	}
	sid, err := hex.DecodeString(m[2])
	if err != nil {
		return TraceContext{}, fmt.Errorf("%w: span_id hex: %v", ErrInvalidTraceparent, err)
	}
	flags, err := hex.DecodeString(m[3])
	if err != nil {
		return TraceContext{}, fmt.Errorf("%w: flags hex: %v", ErrInvalidTraceparent, err)
	}
	var tc TraceContext
	copy(tc.TraceID[:], tcid)
	copy(tc.SpanID[:], sid)
	tc.Flags = flags[0]

	// W3C requires both IDs to be non-zero.
	zeroT := true
	for _, b := range tc.TraceID {
		if b != 0 {
			zeroT = false
			break
		}
	}
	if zeroT {
		return TraceContext{}, ErrZeroTraceID
	}
	zeroS := true
	for _, b := range tc.SpanID {
		if b != 0 {
			zeroS = false
			break
		}
	}
	if zeroS {
		return TraceContext{}, ErrZeroSpanID
	}
	return tc, nil
}

// NewTraceContext mints a new TraceContext with random TraceID and SpanID.
// Used to start a NEW trace (request entering the gateway with no
// traceparent header). For downstream span creation, see Tracer.StartSpan.
func NewTraceContext() (TraceContext, error) {
	var tc TraceContext
	if _, err := rand.Read(tc.TraceID[:]); err != nil {
		return TraceContext{}, fmt.Errorf("tracing: NewTraceContext: %w", err)
	}
	if _, err := rand.Read(tc.SpanID[:]); err != nil {
		return TraceContext{}, fmt.Errorf("tracing: NewTraceContext: %w", err)
	}
	// Default to sampled=false; sampler decides.
	tc.Flags = 0
	return tc, nil
}
