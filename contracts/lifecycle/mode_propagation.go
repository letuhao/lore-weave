package lifecycle

import (
	"encoding/json"
	"errors"
	"fmt"
)

// ControlChannel is the canonical Redis pubsub channel for mode-shift events.
// Q-L1J-1 LOCKED 2026-05-29: shared with cache Redis (lower infra footprint).
// Risk documented in runbooks/degraded_mode/recovery.md: if Redis itself
// dies, the propagation degrades to per-service health-check polling.
const ControlChannel = "lw:dependency:control"

// MessageVersion is the wire-format version. Bump on breaking changes; all
// services accept N + N-1 during rollouts.
const MessageVersion = 1

// MessageKind discriminates control messages on the shared channel.
type MessageKind string

const (
	// KindModeShift announces a mode change. Pattern: publish-fanout
	// (per Q-L1J-1 implementation note in cycle brief) — every subscriber
	// receives every shift; no request/response.
	KindModeShift MessageKind = "mode_shift"

	// KindModeProbe is an idempotent "what mode are you in?" query —
	// every subscriber answers with its own KindModeShift carrying its
	// current mode. Used by SRE dashboard refresh.
	KindModeProbe MessageKind = "mode_probe"

	// KindWsDisconnectUser instructs the api-gateway-bff WS server to
	// forcibly close every live WebSocket belonging to the named
	// `user_ref_id`. Used by:
	//   * auth-service on logout / token revocation (close 4002)
	//   * admin tooling on force-kick (close 4005)
	//   * S8 crypto-shred on user-erasure (close 4003)
	//   * S10 reality archive on realities-revoked (close 4004)
	//   * compromise-detection on fingerprint regression (close 4009)
	// Added cycle 29 L6.D — channel is shared with the cycle 7 mode-shift
	// fanout (single Redis pubsub topic; subscribers ignore message kinds
	// they don't care about). The propagation SLA is < 1s end-to-end.
	KindWsDisconnectUser MessageKind = "ws_disconnect_user"
)

// ControlMessage is the wire envelope.
//
// Wire format example (KindModeShift, Full → Limited):
//
//	{
//	  "version": 1,
//	  "kind": "mode_shift",
//	  "service": "world-service",
//	  "instance": "world-service-7f2c",
//	  "from_mode": "full",
//	  "to_mode": "limited",
//	  "reason": "meta_primary_unreachable",
//	  "ts_nanos": 1716960000000000000
//	}
//
// On KindModeProbe, `from_mode`/`to_mode` are empty and `service`/`instance`
// are the requester's identity (subscribers ignore probes from themselves).
type ControlMessage struct {
	Version  int         `json:"version"`
	Kind     MessageKind `json:"kind"`
	Service  string      `json:"service"`
	Instance string      `json:"instance"`
	FromMode string      `json:"from_mode,omitempty"`
	ToMode   string      `json:"to_mode,omitempty"`
	Reason   string      `json:"reason,omitempty"`
	TsNanos  int64       `json:"ts_nanos"`

	// L6.D cycle 29 — populated on KindWsDisconnectUser. UserRefID is
	// REQUIRED; CloseCode is one of the 11 codes in
	// contracts/ws/envelope.go::CloseCode (1000 / 4001..4010). NonceID
	// provides idempotency — subscribers de-dupe on a small LRU.
	UserRefID string `json:"user_ref_id,omitempty"`
	CloseCode uint16 `json:"close_code,omitempty"`
	NonceID   string `json:"nonce_id,omitempty"`
}

// ErrInvalidControlMessage is returned by DecodeControlMessage when the
// envelope is malformed or carries an unsupported version.
var ErrInvalidControlMessage = errors.New("lifecycle: invalid control message")

// EncodeModeShift builds the JSON wire bytes for a mode shift.
func EncodeModeShift(service, instance string, fromMode, toMode ServiceMode, reason string, tsNanos int64) ([]byte, error) {
	if service == "" {
		return nil, fmt.Errorf("%w: service empty", ErrInvalidControlMessage)
	}
	if instance == "" {
		return nil, fmt.Errorf("%w: instance empty", ErrInvalidControlMessage)
	}
	if reason == "" {
		return nil, fmt.Errorf("%w: reason empty", ErrInvalidControlMessage)
	}
	msg := ControlMessage{
		Version:  MessageVersion,
		Kind:     KindModeShift,
		Service:  service,
		Instance: instance,
		FromMode: fromMode.String(),
		ToMode:   toMode.String(),
		Reason:   reason,
		TsNanos:  tsNanos,
	}
	return json.Marshal(msg)
}

// EncodeWsDisconnectUser builds a JSON wire message instructing the
// api-gateway-bff WS server to forcibly close every connection belonging
// to `userRefID`. `closeCode` MUST be one of the 11 codes in
// contracts/ws/envelope.go::CloseCode (1000 or 4001..4010). `nonceID`
// (UUID recommended) supplies idempotency — subscribers de-dupe.
//
// Cycle 29 L6.D — reuses the cycle 7 control channel (no new topic).
func EncodeWsDisconnectUser(service, instance, userRefID string, closeCode uint16, reason, nonceID string, tsNanos int64) ([]byte, error) {
	if service == "" {
		return nil, fmt.Errorf("%w: service empty", ErrInvalidControlMessage)
	}
	if instance == "" {
		return nil, fmt.Errorf("%w: instance empty", ErrInvalidControlMessage)
	}
	if userRefID == "" {
		return nil, fmt.Errorf("%w: user_ref_id empty", ErrInvalidControlMessage)
	}
	if reason == "" {
		return nil, fmt.Errorf("%w: reason empty", ErrInvalidControlMessage)
	}
	if nonceID == "" {
		return nil, fmt.Errorf("%w: nonce_id empty (idempotency required)", ErrInvalidControlMessage)
	}
	if !validWsCloseCode(closeCode) {
		return nil, fmt.Errorf("%w: close_code %d not in {1000, 4001..4010}", ErrInvalidControlMessage, closeCode)
	}
	msg := ControlMessage{
		Version:   MessageVersion,
		Kind:      KindWsDisconnectUser,
		Service:   service,
		Instance:  instance,
		Reason:    reason,
		TsNanos:   tsNanos,
		UserRefID: userRefID,
		CloseCode: closeCode,
		NonceID:   nonceID,
	}
	return json.Marshal(msg)
}

// validWsCloseCode mirrors the 11 close codes defined in
// contracts/ws/envelope.go::CloseCode + crates/contracts-ws/close_codes.rs.
// Kept inline so the lifecycle package stays free of a back-dep on
// contracts/ws (the dependency direction is gateway → lifecycle, not
// the other way).
func validWsCloseCode(c uint16) bool {
	if c == 1000 {
		return true
	}
	return c >= 4001 && c <= 4010
}

// EncodeModeProbe builds a probe message (requester announces itself; every
// subscriber replies with its own mode_shift carrying its current mode).
func EncodeModeProbe(service, instance string, tsNanos int64) ([]byte, error) {
	if service == "" {
		return nil, fmt.Errorf("%w: service empty", ErrInvalidControlMessage)
	}
	if instance == "" {
		return nil, fmt.Errorf("%w: instance empty", ErrInvalidControlMessage)
	}
	msg := ControlMessage{
		Version:  MessageVersion,
		Kind:     KindModeProbe,
		Service:  service,
		Instance: instance,
		TsNanos:  tsNanos,
	}
	return json.Marshal(msg)
}

// DecodeControlMessage parses a wire-format envelope; rejects on unsupported
// version, unknown kind, or missing required fields. Callers MUST drop
// (with a metric) rather than crash on a decode error — adversary safety.
func DecodeControlMessage(data []byte) (ControlMessage, error) {
	var msg ControlMessage
	if err := json.Unmarshal(data, &msg); err != nil {
		return msg, fmt.Errorf("%w: %v", ErrInvalidControlMessage, err)
	}
	if msg.Version != MessageVersion {
		return msg, fmt.Errorf("%w: unsupported version %d", ErrInvalidControlMessage, msg.Version)
	}
	switch msg.Kind {
	case KindModeShift:
		if msg.FromMode == "" || msg.ToMode == "" {
			return msg, fmt.Errorf("%w: mode_shift missing from/to mode", ErrInvalidControlMessage)
		}
		if _, err := ParseServiceMode(msg.FromMode); err != nil {
			return msg, fmt.Errorf("%w: %v", ErrInvalidControlMessage, err)
		}
		if _, err := ParseServiceMode(msg.ToMode); err != nil {
			return msg, fmt.Errorf("%w: %v", ErrInvalidControlMessage, err)
		}
		if msg.Reason == "" {
			return msg, fmt.Errorf("%w: mode_shift missing reason", ErrInvalidControlMessage)
		}
	case KindModeProbe:
		// Probes carry only requester identity; nothing else to validate.
	case KindWsDisconnectUser:
		// L6.D cycle 29.
		if msg.UserRefID == "" {
			return msg, fmt.Errorf("%w: ws_disconnect_user missing user_ref_id", ErrInvalidControlMessage)
		}
		if !validWsCloseCode(msg.CloseCode) {
			return msg, fmt.Errorf("%w: ws_disconnect_user invalid close_code %d", ErrInvalidControlMessage, msg.CloseCode)
		}
		if msg.NonceID == "" {
			return msg, fmt.Errorf("%w: ws_disconnect_user missing nonce_id (idempotency)", ErrInvalidControlMessage)
		}
		if msg.Reason == "" {
			return msg, fmt.Errorf("%w: ws_disconnect_user missing reason", ErrInvalidControlMessage)
		}
	default:
		return msg, fmt.Errorf("%w: unknown kind %q", ErrInvalidControlMessage, msg.Kind)
	}
	if msg.Service == "" || msg.Instance == "" || msg.TsNanos <= 0 {
		return msg, fmt.Errorf("%w: missing required identity/timestamp fields", ErrInvalidControlMessage)
	}
	return msg, nil
}
