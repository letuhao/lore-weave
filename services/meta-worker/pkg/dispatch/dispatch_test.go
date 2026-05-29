package dispatch

import (
	"context"
	"errors"
	"strings"
	"testing"
)

func TestDispatcher_RegisterAndDispatch(t *testing.T) {
	d := New()
	called := false
	d.Register("xreality.canon.promoted", func(_ context.Context, _ map[string]any) error {
		called = true
		return nil
	})
	err := d.Dispatch(context.Background(), "xreality.canon.promoted", map[string]any{"x": 1})
	if err != nil {
		t.Fatal(err)
	}
	if !called {
		t.Error("handler not called")
	}
}

func TestDispatch_NoHandlerReturnsErrNoHandler(t *testing.T) {
	d := New()
	err := d.Dispatch(context.Background(), "xreality.unknown.event", nil)
	if err == nil {
		t.Fatal("expected ErrNoHandler")
	}
	if !errors.Is(err, ErrNoHandler) {
		t.Errorf("expected ErrNoHandler, got %v", err)
	}
}

func TestRegister_PanicsOnEmptyType(t *testing.T) {
	defer func() {
		if recover() == nil {
			t.Error("expected panic on empty event_type")
		}
	}()
	New().Register("", func(_ context.Context, _ map[string]any) error { return nil })
}

func TestRegister_PanicsOnNilHandler(t *testing.T) {
	defer func() {
		if recover() == nil {
			t.Error("expected panic on nil handler")
		}
	}()
	New().Register("xreality.x.y", nil)
}

func TestValidateAllowlist_RejectsNonXReality(t *testing.T) {
	d := New()
	d.Register("npc.said", func(_ context.Context, _ map[string]any) error { return nil })
	err := d.ValidateAllowlist()
	if err == nil {
		t.Fatal("expected I7 violation error")
	}
	if !strings.Contains(err.Error(), "npc.said") {
		t.Errorf("expected error to name the bad event_type, got %v", err)
	}
}

func TestValidateAllowlist_AcceptsXRealityOnly(t *testing.T) {
	d := New()
	d.Register("xreality.canon.promoted", func(_ context.Context, _ map[string]any) error { return nil })
	d.Register("xreality.user.erased", func(_ context.Context, _ map[string]any) error { return nil })
	if err := d.ValidateAllowlist(); err != nil {
		t.Errorf("expected nil error, got %v", err)
	}
}

func TestRegistered_ReturnsSortedList(t *testing.T) {
	d := New()
	d.Register("xreality.user.erased", func(_ context.Context, _ map[string]any) error { return nil })
	d.Register("xreality.canon.promoted", func(_ context.Context, _ map[string]any) error { return nil })
	got := d.Registered()
	want := []string{"xreality.canon.promoted", "xreality.user.erased"}
	if len(got) != len(want) {
		t.Fatalf("got %v want %v", got, want)
	}
	for i := range got {
		if got[i] != want[i] {
			t.Errorf("position %d: got %s want %s", i, got[i], want[i])
		}
	}
}

func TestNewWithSkeletons_CapturesEveryDispatch(t *testing.T) {
	sink := &SkeletonSink{}
	d := NewWithSkeletons(sink)
	if err := d.ValidateAllowlist(); err != nil {
		t.Fatalf("skeleton dispatcher should pass allowlist: %v", err)
	}
	_ = d.Dispatch(context.Background(), "xreality.canon.promoted", map[string]any{"entry_id": "e1"})
	_ = d.Dispatch(context.Background(), "xreality.user.erased", map[string]any{"user_id": "u1"})
	got := sink.Records()
	if len(got) != 2 {
		t.Fatalf("expected 2 captured dispatches, got %d", len(got))
	}
	if got[0].EventType != "xreality.canon.promoted" {
		t.Errorf("first record event_type=%s", got[0].EventType)
	}
	if got[1].EventType != "xreality.user.erased" {
		t.Errorf("second record event_type=%s", got[1].EventType)
	}
}

func TestSkeletonSink_DefensiveCopy(t *testing.T) {
	sink := &SkeletonSink{}
	sink.Append(SkeletonRecord{EventType: "xreality.x.y", Fields: map[string]any{"k": "v"}})
	// Mutate the caller's map.
	rec := sink.Records()[0]
	rec.Fields["k"] = "MUTATED"
	// Sink's copy should be untouched.
	if sink.Records()[0].Fields["k"] != "v" {
		t.Errorf("defensive copy broken — sink mutated by caller")
	}
}
