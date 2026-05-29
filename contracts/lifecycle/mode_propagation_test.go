package lifecycle

import (
	"encoding/json"
	"errors"
	"strings"
	"testing"
)

func TestEncodeModeShift_RoundTripDecode(t *testing.T) {
	raw, err := EncodeModeShift("world-service", "world-service-7f2c", ModeFull, ModeLimited, "meta_primary_unreachable", 1716960000000000000)
	if err != nil {
		t.Fatalf("EncodeModeShift err=%v", err)
	}
	msg, err := DecodeControlMessage(raw)
	if err != nil {
		t.Fatalf("DecodeControlMessage err=%v", err)
	}
	if msg.Version != MessageVersion {
		t.Errorf("Version = %d, want %d", msg.Version, MessageVersion)
	}
	if msg.Kind != KindModeShift {
		t.Errorf("Kind = %q, want %q", msg.Kind, KindModeShift)
	}
	if msg.FromMode != "full" || msg.ToMode != "limited" {
		t.Errorf("modes = %q→%q", msg.FromMode, msg.ToMode)
	}
	if msg.Reason != "meta_primary_unreachable" {
		t.Errorf("Reason = %q", msg.Reason)
	}
}

func TestEncodeModeProbe_RoundTripDecode(t *testing.T) {
	raw, err := EncodeModeProbe("sre-dashboard", "sre-dashboard-1", 1716960000000000000)
	if err != nil {
		t.Fatalf("EncodeModeProbe err=%v", err)
	}
	msg, err := DecodeControlMessage(raw)
	if err != nil {
		t.Fatalf("DecodeControlMessage err=%v", err)
	}
	if msg.Kind != KindModeProbe {
		t.Errorf("Kind = %q, want %q", msg.Kind, KindModeProbe)
	}
	if msg.FromMode != "" || msg.ToMode != "" {
		t.Errorf("probe should not carry modes; got %q/%q", msg.FromMode, msg.ToMode)
	}
}

func TestEncodeModeShift_RejectsEmptyRequired(t *testing.T) {
	cases := []struct {
		name, service, instance, reason string
	}{
		{"empty service", "", "i", "r"},
		{"empty instance", "s", "", "r"},
		{"empty reason", "s", "i", ""},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			_, err := EncodeModeShift(c.service, c.instance, ModeFull, ModeLimited, c.reason, 1)
			if !errors.Is(err, ErrInvalidControlMessage) {
				t.Errorf("err = %v, want ErrInvalidControlMessage", err)
			}
		})
	}
}

func TestDecodeControlMessage_RejectsUnknownKind(t *testing.T) {
	raw := []byte(`{"version":1,"kind":"weather_report","service":"s","instance":"i","ts_nanos":1}`)
	_, err := DecodeControlMessage(raw)
	if !errors.Is(err, ErrInvalidControlMessage) {
		t.Errorf("err = %v, want ErrInvalidControlMessage", err)
	}
}

func TestDecodeControlMessage_RejectsUnsupportedVersion(t *testing.T) {
	raw := []byte(`{"version":99,"kind":"mode_probe","service":"s","instance":"i","ts_nanos":1}`)
	_, err := DecodeControlMessage(raw)
	if !errors.Is(err, ErrInvalidControlMessage) {
		t.Errorf("err = %v, want ErrInvalidControlMessage", err)
	}
}

func TestDecodeControlMessage_RejectsInvalidJSON(t *testing.T) {
	_, err := DecodeControlMessage([]byte(`{`))
	if !errors.Is(err, ErrInvalidControlMessage) {
		t.Errorf("err = %v, want ErrInvalidControlMessage", err)
	}
}

func TestDecodeControlMessage_RejectsModeShiftMissingModes(t *testing.T) {
	raw := []byte(`{"version":1,"kind":"mode_shift","service":"s","instance":"i","ts_nanos":1,"reason":"r"}`)
	_, err := DecodeControlMessage(raw)
	if !errors.Is(err, ErrInvalidControlMessage) {
		t.Errorf("err = %v, want ErrInvalidControlMessage", err)
	}
}

func TestDecodeControlMessage_RejectsModeShiftBadMode(t *testing.T) {
	raw := []byte(`{"version":1,"kind":"mode_shift","service":"s","instance":"i","ts_nanos":1,"reason":"r","from_mode":"full","to_mode":"maintenance"}`)
	_, err := DecodeControlMessage(raw)
	if !errors.Is(err, ErrInvalidControlMessage) {
		t.Errorf("err = %v, want ErrInvalidControlMessage", err)
	}
}

func TestControlChannel_ConstantStable(t *testing.T) {
	// Q-L1J-1 LOCKED: shared with cache Redis. Channel name is part of the
	// inter-service contract; changing it forks behavior across versions.
	if ControlChannel != "lw:dependency:control" {
		t.Errorf("ControlChannel drifted: got %q, want %q", ControlChannel, "lw:dependency:control")
	}
}

func TestEncodeModeShift_WireFormatStable(t *testing.T) {
	// Pin the wire format so a future change is a visible test break.
	raw, err := EncodeModeShift("svc", "inst", ModeFull, ModeReadOnly, "drill", 1716960000000000000)
	if err != nil {
		t.Fatal(err)
	}
	var generic map[string]any
	if err := json.Unmarshal(raw, &generic); err != nil {
		t.Fatal(err)
	}
	// Required keys must all be present.
	for _, k := range []string{"version", "kind", "service", "instance", "from_mode", "to_mode", "reason", "ts_nanos"} {
		if _, ok := generic[k]; !ok {
			t.Errorf("wire format missing key %q (full payload: %s)", k, string(raw))
		}
	}
	if !strings.Contains(string(raw), `"kind":"mode_shift"`) {
		t.Errorf("expected kind=mode_shift literal; got %s", string(raw))
	}
}
