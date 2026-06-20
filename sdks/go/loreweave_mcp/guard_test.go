package loreweave_mcp

import (
	"context"
	"errors"
	"testing"

	"github.com/google/uuid"
	"github.com/loreweave/grantclient"
)

// fakeGrants is a test double for GrantChecker.
type fakeGrants struct {
	err error // returned from RequireGrant
}

func (f fakeGrants) RequireGrant(_ context.Context, _, _ uuid.UUID, _ GrantLevel) error {
	return f.err
}

func TestBookOwnerGuard(t *testing.T) {
	ctx := context.Background()
	user := uuid.New()
	book := uuid.New()

	t.Run("happy", func(t *testing.T) {
		g := BookOwnerGuard(fakeGrants{err: nil}, GrantEdit)
		if err := g.Check(ctx, user, book); err != nil {
			t.Fatalf("Check = %v, want nil", err)
		}
	})

	t.Run("denied collapses to not-accessible", func(t *testing.T) {
		g := BookOwnerGuard(fakeGrants{err: grantclient.ErrForbidden}, GrantEdit)
		if err := g.Check(ctx, user, book); !errors.Is(err, ErrNotAccessible) {
			t.Fatalf("Check = %v, want ErrNotAccessible", err)
		}
	})

	t.Run("authority outage fails closed as unavailable", func(t *testing.T) {
		g := BookOwnerGuard(fakeGrants{err: grantclient.ErrUnavailable}, GrantEdit)
		if err := g.Check(ctx, user, book); !errors.Is(err, ErrCheckUnavailable) {
			t.Fatalf("Check = %v, want ErrCheckUnavailable", err)
		}
	})

	t.Run("unknown error fails closed", func(t *testing.T) {
		g := BookOwnerGuard(fakeGrants{err: errors.New("boom")}, GrantEdit)
		if err := g.Check(ctx, user, book); err == nil {
			t.Fatal("Check = nil, want a deny error")
		}
	})

	t.Run("nil grants fails closed", func(t *testing.T) {
		g := BookOwnerGuard(nil, GrantEdit)
		if err := g.Check(ctx, user, book); !errors.Is(err, ErrCheckUnavailable) {
			t.Fatalf("Check = %v, want ErrCheckUnavailable", err)
		}
	})
}

func TestUserScopeGuard(t *testing.T) {
	ctx := context.Background()
	caller := uuid.New()
	res := uuid.New()

	t.Run("happy — resource owned by caller", func(t *testing.T) {
		g := UserScopeGuard(func(context.Context, uuid.UUID) (uuid.UUID, error) {
			return caller, nil
		})
		if err := g.Check(ctx, caller, res); err != nil {
			t.Fatalf("Check = %v, want nil", err)
		}
	})

	t.Run("denied — resource owned by someone else", func(t *testing.T) {
		other := uuid.New()
		g := UserScopeGuard(func(context.Context, uuid.UUID) (uuid.UUID, error) {
			return other, nil
		})
		if err := g.Check(ctx, caller, res); !errors.Is(err, ErrNotAccessible) {
			t.Fatalf("Check = %v, want ErrNotAccessible", err)
		}
	})

	t.Run("lookup error fails closed (no oracle)", func(t *testing.T) {
		g := UserScopeGuard(func(context.Context, uuid.UUID) (uuid.UUID, error) {
			return uuid.Nil, errors.New("not found")
		})
		if err := g.Check(ctx, caller, res); !errors.Is(err, ErrNotAccessible) {
			t.Fatalf("Check = %v, want ErrNotAccessible", err)
		}
	})

	t.Run("authority outage → try again", func(t *testing.T) {
		g := UserScopeGuard(func(context.Context, uuid.UUID) (uuid.UUID, error) {
			return uuid.Nil, grantclient.ErrUnavailable
		})
		if err := g.Check(ctx, caller, res); !errors.Is(err, ErrCheckUnavailable) {
			t.Fatalf("Check = %v, want ErrCheckUnavailable", err)
		}
	})

	t.Run("nil ownerOf fails closed", func(t *testing.T) {
		g := UserScopeGuard(nil)
		if err := g.Check(ctx, caller, res); !errors.Is(err, ErrNotAccessible) {
			t.Fatalf("Check = %v, want ErrNotAccessible", err)
		}
	})

	// The "zero UUID owns everything" defense: a row whose owner resolves to
	// uuid.Nil (a NULL/zero owner column) with NO error MUST be denied — even if
	// the caller themselves were somehow uuid.Nil — so a zero owner can never grant
	// access. The owner==uuid.Nil branch in the guard exists precisely for this.
	t.Run("nil owner with nil error denied (zero owns nothing)", func(t *testing.T) {
		g := UserScopeGuard(func(context.Context, uuid.UUID) (uuid.UUID, error) {
			return uuid.Nil, nil // row exists but has a zero/NULL owner
		})
		if err := g.Check(ctx, caller, res); !errors.Is(err, ErrNotAccessible) {
			t.Fatalf("Check = %v, want ErrNotAccessible (zero owner must never grant)", err)
		}
		// Even a zero-UUID caller must not match a zero owner.
		if err := g.Check(ctx, uuid.Nil, res); !errors.Is(err, ErrNotAccessible) {
			t.Fatalf("Check(caller=Nil) = %v, want ErrNotAccessible", err)
		}
	})
}

func TestProjectGuard(t *testing.T) {
	ctx := context.Background()
	caller := uuid.New()
	proj := uuid.New()

	t.Run("happy", func(t *testing.T) {
		g := ProjectGuard(func(context.Context, uuid.UUID) (uuid.UUID, error) {
			return caller, nil
		})
		if err := g.Check(ctx, caller, proj); err != nil {
			t.Fatalf("Check = %v, want nil", err)
		}
	})

	t.Run("denied — project owned by another user", func(t *testing.T) {
		g := ProjectGuard(func(context.Context, uuid.UUID) (uuid.UUID, error) {
			return uuid.New(), nil
		})
		if err := g.Check(ctx, caller, proj); !errors.Is(err, ErrNotAccessible) {
			t.Fatalf("Check = %v, want ErrNotAccessible", err)
		}
	})

	t.Run("lookup error fails closed", func(t *testing.T) {
		g := ProjectGuard(func(context.Context, uuid.UUID) (uuid.UUID, error) {
			return uuid.Nil, errors.New("boom")
		})
		if err := g.Check(ctx, caller, proj); !errors.Is(err, ErrNotAccessible) {
			t.Fatalf("Check = %v, want ErrNotAccessible", err)
		}
	})

	t.Run("nil ownerOf fails closed", func(t *testing.T) {
		g := ProjectGuard(nil)
		if err := g.Check(ctx, caller, proj); !errors.Is(err, ErrNotAccessible) {
			t.Fatalf("Check = %v, want ErrNotAccessible", err)
		}
	})
}

func TestUniformNotAccessible(t *testing.T) {
	if err := UniformNotAccessible(nil); err != nil {
		t.Errorf("nil → %v, want nil", err)
	}
	if err := UniformNotAccessible(grantclient.ErrUnavailable); !errors.Is(err, ErrCheckUnavailable) {
		t.Errorf("ErrUnavailable → %v, want ErrCheckUnavailable", err)
	}
	if err := UniformNotAccessible(ErrCheckUnavailable); !errors.Is(err, ErrCheckUnavailable) {
		t.Errorf("ErrCheckUnavailable → %v, want ErrCheckUnavailable", err)
	}
	// not-found and forbidden both collapse to the SAME not-accessible (no oracle).
	if err := UniformNotAccessible(errors.New("sql: no rows")); !errors.Is(err, ErrNotAccessible) {
		t.Errorf("not-found → %v, want ErrNotAccessible", err)
	}
	if err := UniformNotAccessible(grantclient.ErrForbidden); !errors.Is(err, ErrNotAccessible) {
		t.Errorf("forbidden → %v, want ErrNotAccessible", err)
	}
}
