package ws

import (
	"errors"
	"testing"
)

func TestServiceMode_String(t *testing.T) {
	cases := map[ServiceMode]string{
		ModeFull:       "full",
		ModeLimited:    "limited",
		ModeEssentials: "essentials",
		ModeReadOnly:   "read_only",
		ModeOffline:    "offline",
	}
	for m, want := range cases {
		if got := m.String(); got != want {
			t.Errorf("ServiceMode(%d).String = %q; want %q (parity with contracts/lifecycle)", int(m), got, want)
		}
	}
}

func TestServiceMode_IsValid(t *testing.T) {
	for _, m := range []ServiceMode{ModeFull, ModeLimited, ModeEssentials, ModeReadOnly, ModeOffline} {
		if !m.IsValid() {
			t.Errorf("IsValid(%v) = false; want true", m)
		}
	}
	if ServiceMode(99).IsValid() {
		t.Errorf("IsValid(99) = true; want false")
	}
}

func TestServiceMode_AcceptsWrites(t *testing.T) {
	tests := map[ServiceMode]bool{
		ModeFull:       true,
		ModeLimited:    true,
		ModeEssentials: false,
		ModeReadOnly:   false,
		ModeOffline:    false,
	}
	for m, want := range tests {
		if got := m.AcceptsWrites(); got != want {
			t.Errorf("%v.AcceptsWrites = %v; want %v", m, got, want)
		}
	}
}

func TestServiceMode_AcceptsEssentialWrites(t *testing.T) {
	tests := map[ServiceMode]bool{
		ModeFull:       true,
		ModeLimited:    true,
		ModeEssentials: true,
		ModeReadOnly:   false,
		ModeOffline:    false,
	}
	for m, want := range tests {
		if got := m.AcceptsEssentialWrites(); got != want {
			t.Errorf("%v.AcceptsEssentialWrites = %v; want %v", m, got, want)
		}
	}
}

func TestServiceModeGate_ControlAlwaysAccepted(t *testing.T) {
	g := ServiceModeGate{Provider: StaticMode(ModeOffline)}
	env := Envelope{
		Version: EnvelopeVersion, Kind: KindControl, Type: "ws.ping",
		Direction: DirectionClientToServer,
	}
	if err := g.Check(env, false); err != nil {
		t.Errorf("control envelope in Offline = err %v; want nil (control bypass)", err)
	}
}

func TestServiceModeGate_ReadOnlyRejectsData(t *testing.T) {
	g := ServiceModeGate{Provider: StaticMode(ModeReadOnly)}
	env := Envelope{
		Version: EnvelopeVersion, Kind: KindData, Type: "chat.message",
		Direction: DirectionClientToServer, Seq: 1, Nonce: "n1",
	}
	err := g.Check(env, false)
	if err == nil {
		t.Fatalf("data envelope in ReadOnly = nil; want rejection")
	}
	if !errors.Is(err, ErrModeRejected) {
		t.Errorf("err = %v; want wraps ErrModeRejected", err)
	}
	if !errors.Is(err, ErrModeRejectsWrites) {
		t.Errorf("err = %v; want wraps ErrModeRejectsWrites", err)
	}
}

func TestServiceModeGate_OfflineRejectsData(t *testing.T) {
	g := ServiceModeGate{Provider: StaticMode(ModeOffline)}
	env := Envelope{
		Version: EnvelopeVersion, Kind: KindData, Type: "chat.message",
		Direction: DirectionClientToServer, Seq: 1, Nonce: "n1",
	}
	if err := g.Check(env, false); !errors.Is(err, ErrModeRejected) {
		t.Errorf("Offline data check err = %v; want ErrModeRejected", err)
	}
}

func TestServiceModeGate_FullAcceptsData(t *testing.T) {
	g := ServiceModeGate{Provider: StaticMode(ModeFull)}
	env := Envelope{
		Version: EnvelopeVersion, Kind: KindData, Type: "chat.message",
		Direction: DirectionClientToServer, Seq: 1, Nonce: "n1",
	}
	if err := g.Check(env, false); err != nil {
		t.Errorf("Full data check err = %v; want nil", err)
	}
}

func TestServiceModeGate_EssentialsAcceptsEssentialOnly(t *testing.T) {
	g := ServiceModeGate{Provider: StaticMode(ModeEssentials)}
	env := Envelope{
		Version: EnvelopeVersion, Kind: KindData, Type: "chat.message",
		Direction: DirectionClientToServer, Seq: 1, Nonce: "n1",
	}
	if err := g.Check(env, false); err == nil {
		t.Errorf("Essentials + non-essential = nil; want rejection")
	} else if !errors.Is(err, ErrModeRejectsScope) {
		t.Errorf("err = %v; want wraps ErrModeRejectsScope", err)
	}
	// Same envelope but caller marks it essential (e.g., session heartbeat).
	if err := g.Check(env, true); err != nil {
		t.Errorf("Essentials + essential=true err = %v; want nil", err)
	}
}

func TestServiceModeGate_NilProviderDefaultsToAccept(t *testing.T) {
	g := ServiceModeGate{}
	env := Envelope{
		Version: EnvelopeVersion, Kind: KindData, Type: "chat.message",
		Direction: DirectionClientToServer, Seq: 1, Nonce: "n1",
	}
	if err := g.Check(env, false); err != nil {
		t.Errorf("nil-provider gate err = %v; want nil (defensive default)", err)
	}
}

func TestServiceModeGate_InvalidModeRejected(t *testing.T) {
	g := ServiceModeGate{Provider: StaticMode(99)}
	env := Envelope{
		Version: EnvelopeVersion, Kind: KindData, Type: "chat.message",
		Direction: DirectionClientToServer, Seq: 1, Nonce: "n1",
	}
	if err := g.Check(env, false); err == nil {
		t.Errorf("invalid mode = nil err; want validation err")
	}
}
