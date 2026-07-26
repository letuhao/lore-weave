package loreweave_mcp

import (
	"context"
	"testing"

	"github.com/google/uuid"
)

func TestResolveBookScope(t *testing.T) {
	ambient := uuid.New()
	other := uuid.New()
	bound := ContextWithBookID(context.Background(), ambient.String())
	unbound := context.Background()

	t.Run("omitted arg on bound surface → ambient (envelope)", func(t *testing.T) {
		s, ok := ResolveBookScope(bound, "")
		if !ok || s.BookID != ambient || s.Source != "envelope" || s.CrossBook {
			t.Fatalf("got %+v ok=%v, want ambient/envelope/not-cross", s, ok)
		}
	})

	t.Run("explicit arg == ambient → arg, not cross", func(t *testing.T) {
		s, ok := ResolveBookScope(bound, ambient.String())
		if !ok || s.BookID != ambient || s.Source != "arg" || s.CrossBook {
			t.Fatalf("got %+v ok=%v, want ambient/arg/not-cross", s, ok)
		}
	})

	t.Run("explicit DIFFERENT valid arg → cross-book", func(t *testing.T) {
		s, ok := ResolveBookScope(bound, other.String())
		if !ok || s.BookID != other || s.Source != "arg" || !s.CrossBook {
			t.Fatalf("got %+v ok=%v, want other/arg/CROSS", s, ok)
		}
	})

	t.Run("malformed arg + ambient → silent repair, NOT cross", func(t *testing.T) {
		s, ok := ResolveBookScope(bound, "not-a-uuid")
		if !ok || s.BookID != ambient || s.Source != "envelope" || s.CrossBook {
			t.Fatalf("got %+v ok=%v, want ambient/envelope/not-cross (repair)", s, ok)
		}
	})

	t.Run("valid arg, no ambient (external) → arg, not cross", func(t *testing.T) {
		s, ok := ResolveBookScope(unbound, other.String())
		if !ok || s.BookID != other || s.Source != "arg" || s.CrossBook {
			t.Fatalf("got %+v ok=%v, want other/arg/not-cross", s, ok)
		}
	})

	t.Run("blank arg, no ambient → fail-closed", func(t *testing.T) {
		if _, ok := ResolveBookScope(unbound, ""); ok {
			t.Fatal("want ok=false (required-arg) when neither arg nor ambient present")
		}
	})

	t.Run("malformed arg, no ambient → fail-closed", func(t *testing.T) {
		if _, ok := ResolveBookScope(unbound, "nope"); ok {
			t.Fatal("want ok=false (invalid-arg) when malformed and no ambient")
		}
	})
}
