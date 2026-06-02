package ws

import (
	"encoding/json"
	"testing"
)

func TestEnvelope_RoundTrip(t *testing.T) {
	e := Envelope{
		Version:   EnvelopeVersion,
		Kind:      KindData,
		Type:      "chat.message",
		Direction: DirectionClientToServer,
		Seq:       42,
		Nonce:     "01h7x000",
		Payload:   json.RawMessage(`{"text":"hello"}`),
	}
	raw, err := json.Marshal(e)
	if err != nil {
		t.Fatalf("marshal err = %v", err)
	}
	var got Envelope
	if err := json.Unmarshal(raw, &got); err != nil {
		t.Fatalf("unmarshal err = %v", err)
	}
	if got.Version != e.Version || got.Type != e.Type || got.Seq != e.Seq || got.Nonce != e.Nonce {
		t.Errorf("round-trip mismatch: got %+v want %+v", got, e)
	}
	if string(got.Payload) != string(e.Payload) {
		t.Errorf("payload round-trip mismatch")
	}
}

func TestEnvelope_Validate_Happy(t *testing.T) {
	e := Envelope{
		Version:   EnvelopeVersion,
		Kind:      KindData,
		Type:      "chat.message",
		Direction: DirectionClientToServer,
		Seq:       1,
		Nonce:     "n1",
	}
	if err := e.Validate(); err != nil {
		t.Fatalf("Validate err = %v; want nil", err)
	}
}

func TestEnvelope_Validate_VersionMismatch(t *testing.T) {
	e := Envelope{Version: 999, Kind: KindControl, Type: "ws.ping", Direction: DirectionClientToServer}
	if err := e.Validate(); err == nil {
		t.Fatalf("Validate = nil; want version-mismatch error")
	}
}

func TestEnvelope_Validate_BadKind(t *testing.T) {
	e := Envelope{Version: EnvelopeVersion, Kind: "bogus", Type: "ws.ping", Direction: DirectionClientToServer}
	if err := e.Validate(); err == nil {
		t.Fatalf("Validate = nil; want bad-kind error")
	}
}

func TestEnvelope_Validate_BadDirection(t *testing.T) {
	e := Envelope{Version: EnvelopeVersion, Kind: KindControl, Type: "ws.ping", Direction: "x"}
	if err := e.Validate(); err == nil {
		t.Fatalf("Validate = nil; want bad-direction error")
	}
}

func TestEnvelope_Validate_DataRequiresNonce(t *testing.T) {
	e := Envelope{Version: EnvelopeVersion, Kind: KindData, Type: "chat.message", Direction: DirectionClientToServer, Seq: 1}
	if err := e.Validate(); err == nil {
		t.Fatalf("Validate = nil; want nonce-required error")
	}
}

func TestEnvelope_Validate_ControlNoNonce(t *testing.T) {
	e := Envelope{Version: EnvelopeVersion, Kind: KindControl, Type: "ws.ping", Direction: DirectionClientToServer}
	if err := e.Validate(); err != nil {
		t.Errorf("Validate err = %v; want nil for control no-nonce", err)
	}
}

func TestEnvelope_Validate_DataRequiresSeq(t *testing.T) {
	// Data frame with seq 0 (zero value / "omitted") must be rejected —
	// ws/v1.yaml seq minimum:1, required for data (068 / D-WS-TICKET-WIRE).
	e := Envelope{Version: EnvelopeVersion, Kind: KindData, Type: "chat.message", Direction: DirectionClientToServer, Nonce: "n1"}
	if err := e.Validate(); err == nil {
		t.Fatalf("Validate = nil; want seq>=1 error for data frame with seq 0")
	}
	e.Seq = 1
	if err := e.Validate(); err != nil {
		t.Fatalf("Validate err = %v; want nil once seq>=1", err)
	}
}

func TestEnvelope_Validate_ControlSeqZeroOK(t *testing.T) {
	// Control frames omit seq (0) — must NOT trip the data seq>=1 rule.
	e := Envelope{Version: EnvelopeVersion, Kind: KindControl, Type: "ws.ping", Direction: DirectionClientToServer}
	if err := e.Validate(); err != nil {
		t.Errorf("Validate err = %v; want nil for control seq=0", err)
	}
}

func TestCloseCode_Count(t *testing.T) {
	if got, want := len(AllCloseCodes()), 11; got != want {
		t.Fatalf("AllCloseCodes count = %d; want %d (S12 §12AB.9: 1000 + 4001..4010)", got, want)
	}
}

func TestCloseCode_AllValid(t *testing.T) {
	for _, c := range AllCloseCodes() {
		if !c.IsValid() {
			t.Errorf("IsValid(%d) = false; want true", c)
		}
	}
}

func TestCloseCode_InvalidRejected(t *testing.T) {
	for _, c := range []CloseCode{0, 999, 1001, 4000, 4011, 5000} {
		if c.IsValid() {
			t.Errorf("IsValid(%d) = true; want false (defense against typo / silent V2 drift)", c)
		}
	}
}

func TestCloseCode_StringStable(t *testing.T) {
	cases := map[CloseCode]string{
		CloseNormal:                  "normal_closure",
		CloseTokenExpired:            "token_expired",
		CloseTokenRevoked:            "token_revoked",
		CloseUserErased:              "user_erased",
		CloseRealityArchived:         "reality_archived",
		CloseAdminKick:               "admin_kick",
		CloseRateLimitExceeded:       "rate_limit_exceeded",
		CloseOriginMismatch:          "origin_mismatch",
		CloseConnectionLimitExceeded: "connection_limit_exceeded",
		CloseFingerprintMismatch:     "fingerprint_mismatch",
		CloseSchemaInvalid:           "schema_invalid",
	}
	for c, want := range cases {
		if got := c.String(); got != want {
			t.Errorf("CloseCode(%d).String = %q; want %q", c, got, want)
		}
	}
}
