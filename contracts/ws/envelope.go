package ws

import (
	"encoding/json"
	"errors"
	"fmt"
)

// EnvelopeVersion is the current wire format version. Bumping is a
// cross-language change (Go + Rust mirror in lockstep per Q-L4-1).
const EnvelopeVersion = 1

// MessageKind classifies an envelope as control vs data. Routers
// fast-path control messages (ws.ping / ws.pong / ws.refresh) without
// hitting the authz cache (S12 §12AB.4).
type MessageKind string

const (
	// KindControl — protocol/control messages: ws.ping, ws.pong,
	// ws.refresh, ws.close. Bypasses S2/S3 authz.
	KindControl MessageKind = "control"

	// KindData — application messages: chat.*, session.*, presence.*,
	// event.delivery. Subject to S2/S3 authz on every send/receive.
	KindData MessageKind = "data"
)

// Direction marks who sent the envelope. Used by server-side validators
// to reject server→client message types the client tries to send (and
// vice versa).
type Direction string

const (
	// DirectionClientToServer — inbound to the gateway (chat.message,
	// session.join, ws.refresh, etc.).
	DirectionClientToServer Direction = "c2s"

	// DirectionServerToClient — outbound to the browser (event.delivery,
	// ws.close, presence.update, etc.).
	DirectionServerToClient Direction = "s2c"
)

// Envelope is the wire-shape every WS frame deserializes to. Both
// inbound (client→server) and outbound (server→client) frames use
// the same envelope; Direction + Type let the router dispatch.
//
// The envelope is INTENTIONALLY minimal — payload is opaque JSON
// (gateway routes by Type; downstream service code parses Payload
// per its known schema). Bumping EnvelopeVersion is a wire-contract
// change that requires Rust + browser-lib parity.
type Envelope struct {
	// Version pins the envelope schema. Must equal EnvelopeVersion at
	// runtime; mismatch is a hard reject (close code 4010).
	Version int `json:"v"`

	// Kind = control or data (see MessageKind).
	Kind MessageKind `json:"kind"`

	// Type — message-type string (e.g., "chat.message", "ws.ping",
	// "session.kick"). Foundation does NOT constrain the namespace
	// beyond non-empty; L6 ws-gateway owns the canonical V1 list per
	// S12 §12AB.8.
	Type string `json:"type"`

	// Direction — c2s or s2c (server-side validator rejects mismatches).
	Direction Direction `json:"dir"`

	// Seq — monotonic per-connection per-Type sequence. Server rejects
	// duplicates + out-of-order (tolerance per S12 §12AB.7). Zero is
	// reserved for control messages where seq doesn't apply.
	Seq uint64 `json:"seq,omitempty"`

	// Nonce — UUID string; server tracks in TTL set (60s) for replay
	// defense. Required for data messages; optional for control.
	Nonce string `json:"nonce,omitempty"`

	// Payload — opaque per-type bytes. The gateway routes by Type and
	// hands Payload to the consuming service intact.
	Payload json.RawMessage `json:"payload,omitempty"`
}

// Validate enforces envelope-level shape invariants. Per-Type field
// validation is owned by the L6 router (cycle 27+).
func (e Envelope) Validate() error {
	if e.Version != EnvelopeVersion {
		return fmt.Errorf("ws: envelope version %d != current %d", e.Version, EnvelopeVersion)
	}
	switch e.Kind {
	case KindControl, KindData:
	default:
		return fmt.Errorf("ws: invalid envelope kind %q", e.Kind)
	}
	switch e.Direction {
	case DirectionClientToServer, DirectionServerToClient:
	default:
		return fmt.Errorf("ws: invalid envelope direction %q", e.Direction)
	}
	if e.Type == "" {
		return errors.New("ws: envelope type empty")
	}
	if e.Kind == KindData && e.Nonce == "" {
		return errors.New("ws: data envelope requires nonce (replay defense)")
	}
	if e.Kind == KindData && e.Seq < 1 {
		// ws/v1.yaml: seq is `minimum: 1`, required for data, omitted for
		// control. Seq 0 on a data frame is reserved/invalid (it would also
		// trip WSSession.AcceptSeq's "seq=0 reserved for control" guard).
		return errors.New("ws: data envelope requires seq>=1")
	}
	return nil
}

// CloseCode is one of the enumerated S12 §12AB.9 close codes. Wire
// values match WebSocket spec: 1000 + 4001..4010.
type CloseCode uint16

const (
	// CloseNormal — 1000 client-initiated normal closure.
	CloseNormal CloseCode = 1000

	// CloseTokenExpired — 4001 refresh failed before expiry.
	CloseTokenExpired CloseCode = 4001

	// CloseTokenRevoked — 4002 user logout / JWT revoked.
	CloseTokenRevoked CloseCode = 4002

	// CloseUserErased — 4003 S8 crypto-shred fired.
	CloseUserErased CloseCode = 4003

	// CloseRealityArchived — 4004 S10 reality state archived/dropped.
	CloseRealityArchived CloseCode = 4004

	// CloseAdminKick — 4005 S5 Tier 2 Griefing action.
	CloseAdminKick CloseCode = 4005

	// CloseRateLimitExceeded — 4006 persistent L5 violation.
	CloseRateLimitExceeded CloseCode = 4006

	// CloseOriginMismatch — 4007 L4 violation mid-connection.
	CloseOriginMismatch CloseCode = 4007

	// CloseConnectionLimitExceeded — 4008 L5 per-user LRU eviction.
	CloseConnectionLimitExceeded CloseCode = 4008

	// CloseFingerprintMismatch — 4009 L6 client binding broken.
	CloseFingerprintMismatch CloseCode = 4009

	// CloseSchemaInvalid — 4010 persistent malformed messages.
	CloseSchemaInvalid CloseCode = 4010
)

// AllCloseCodes returns every enumerated close code in numeric order.
// Used by tests + the future cross-language conformance lint to
// confirm Go + Rust + (eventually) browser TS lib stay in sync.
func AllCloseCodes() []CloseCode {
	return []CloseCode{
		CloseNormal,
		CloseTokenExpired,
		CloseTokenRevoked,
		CloseUserErased,
		CloseRealityArchived,
		CloseAdminKick,
		CloseRateLimitExceeded,
		CloseOriginMismatch,
		CloseConnectionLimitExceeded,
		CloseFingerprintMismatch,
		CloseSchemaInvalid,
	}
}

// IsValid returns true iff c is one of the enumerated close codes.
// The gateway MUST refuse to close with any other code (defense
// against typos / silent V2 drift).
func (c CloseCode) IsValid() bool {
	for _, ok := range AllCloseCodes() {
		if c == ok {
			return true
		}
	}
	return false
}

// String returns the canonical short name (matches §12AB.9 vocab).
// Used by structured logs + admin tooling.
func (c CloseCode) String() string {
	switch c {
	case CloseNormal:
		return "normal_closure"
	case CloseTokenExpired:
		return "token_expired"
	case CloseTokenRevoked:
		return "token_revoked"
	case CloseUserErased:
		return "user_erased"
	case CloseRealityArchived:
		return "reality_archived"
	case CloseAdminKick:
		return "admin_kick"
	case CloseRateLimitExceeded:
		return "rate_limit_exceeded"
	case CloseOriginMismatch:
		return "origin_mismatch"
	case CloseConnectionLimitExceeded:
		return "connection_limit_exceeded"
	case CloseFingerprintMismatch:
		return "fingerprint_mismatch"
	case CloseSchemaInvalid:
		return "schema_invalid"
	}
	return fmt.Sprintf("invalid_close_code(%d)", uint16(c))
}
