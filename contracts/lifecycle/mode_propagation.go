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
	default:
		return msg, fmt.Errorf("%w: unknown kind %q", ErrInvalidControlMessage, msg.Kind)
	}
	if msg.Service == "" || msg.Instance == "" || msg.TsNanos <= 0 {
		return msg, fmt.Errorf("%w: missing required identity/timestamp fields", ErrInvalidControlMessage)
	}
	return msg, nil
}
