package upcastersgo

import (
	"errors"
	"testing"
)

func TestUpcast_NoOpWhenFromEqualsTo(t *testing.T) {
	r := NewRegistry()
	payload := map[string]any{"text": "hi"}
	out, err := r.Upcast("npc.said", payload, 2, 2)
	if err != nil {
		t.Fatalf("no-op upcast errored: %v", err)
	}
	if len(out) != len(payload) || out["text"] != "hi" {
		t.Errorf("no-op modified payload: %v", out)
	}
}

func TestUpcast_BackwardRejected(t *testing.T) {
	r := NewRegistry()
	_, err := r.Upcast("npc.said", map[string]any{}, 3, 1)
	if err == nil {
		t.Fatal("expected backward upcast error")
	}
	if !IsBackwardUpcast(err) {
		t.Errorf("expected IsBackwardUpcast; got %T %v", err, err)
	}
}

func TestUpcast_MissingHopRejected(t *testing.T) {
	r := NewRegistry()
	_, err := r.Upcast("npc.said", map[string]any{"text": "hi"}, 1, 2)
	if err == nil {
		t.Fatal("expected missing-upcaster error")
	}
	if !IsMissingUpcaster(err) {
		t.Errorf("expected IsMissingUpcaster; got %T %v", err, err)
	}
}

func TestUpcast_NpcSaidV1ToV2Happy(t *testing.T) {
	r := NewRegistry()
	r.Register("npc.said", NpcSaidV1ToV2Upcaster())
	out, err := r.Upcast("npc.said", map[string]any{"text": "hi"}, 1, 2)
	if err != nil {
		t.Fatalf("upcast: %v", err)
	}
	if out["tone"] != "neutral" {
		t.Errorf("expected tone=neutral, got %v", out["tone"])
	}
	if out["text"] != "hi" {
		t.Errorf("preserved field lost: %v", out)
	}
}

func TestUpcast_ChainCompositionEquivalence(t *testing.T) {
	// Verify direct(v1→v3) == staged(v1→v2 then v2→v3)
	v2to3 := &FnUpcaster{From: 2, Fn: func(p map[string]any) (map[string]any, error) {
		out := map[string]any{}
		for k, v := range p {
			out[k] = v
		}
		out["intent"] = "statement"
		return out, nil
	}}
	r := NewRegistry()
	r.Register("npc.said", NpcSaidV1ToV2Upcaster())
	r.Register("npc.said", v2to3)

	direct, err := r.Upcast("npc.said", map[string]any{"text": "hi"}, 1, 3)
	if err != nil {
		t.Fatalf("direct: %v", err)
	}
	mid, err := r.Upcast("npc.said", map[string]any{"text": "hi"}, 1, 2)
	if err != nil {
		t.Fatalf("mid: %v", err)
	}
	staged, err := r.Upcast("npc.said", mid, 2, 3)
	if err != nil {
		t.Fatalf("staged: %v", err)
	}
	if direct["text"] != staged["text"] || direct["tone"] != staged["tone"] || direct["intent"] != staged["intent"] {
		t.Errorf("direct %v != staged %v", direct, staged)
	}
}

func TestUpcast_DuplicateRegistrationPanics(t *testing.T) {
	defer func() {
		r := recover()
		if r == nil {
			t.Fatal("expected panic on duplicate registration")
		}
	}()
	r := NewRegistry()
	r.Register("npc.said", NpcSaidV1ToV2Upcaster())
	r.Register("npc.said", NpcSaidV1ToV2Upcaster())
}

func TestUpcast_PropagatesUpcasterError(t *testing.T) {
	failing := &FnUpcaster{From: 1, Fn: func(_ map[string]any) (map[string]any, error) {
		return nil, errors.New("boom")
	}}
	r := NewRegistry()
	r.Register("foo.bar", failing)
	_, err := r.Upcast("foo.bar", map[string]any{}, 1, 2)
	if err == nil {
		t.Fatal("expected wrapped upcaster error")
	}
	if !IsUpcasterFailed(err) {
		t.Errorf("expected IsUpcasterFailed; got %T %v", err, err)
	}
	if !contains(err.Error(), "boom") {
		t.Errorf("wrapped error should carry original detail: %v", err)
	}
}

func contains(haystack, needle string) bool {
	for i := 0; i+len(needle) <= len(haystack); i++ {
		if haystack[i:i+len(needle)] == needle {
			return true
		}
	}
	return false
}
