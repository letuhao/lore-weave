package bridge

import (
	"strings"
	"testing"

	"github.com/google/uuid"
)

// W6's tenancy tier is decided in exactly one place: deriveOwner. A cold-start
// review of the shipping commit found it had NO test and NO bite -- every
// TestRegister* routes through a fake Registrar, so they exercise the HTTP
// handler and never the decision. Replacing the derivation body with
// `ownerKind := "user"` left the whole Go suite green.
//
// These are the tests that would have gone red.

func TestDeriveOwner_AbsentIsPlatformOwned(t *testing.T) {
	for _, in := range []string{"", "   ", "\t"} {
		kind, id, err := deriveOwner(in)
		if err != nil {
			t.Fatalf("%q: unexpected error: %v", in, err)
		}
		if kind != "system" {
			t.Fatalf("%q: want kind=system, got %q", in, kind)
		}
		if id != nil {
			t.Fatalf("%q: a system-owned reality must carry SQL NULL, got %v", in, id)
		}
	}
}

func TestDeriveOwner_PresentIsUserOwned(t *testing.T) {
	owner := uuid.New()
	kind, id, err := deriveOwner(owner.String())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if kind != "user" {
		t.Fatalf("want kind=user, got %q", kind)
	}
	got, ok := id.(uuid.UUID)
	if !ok || got != owner {
		t.Fatalf("owner did not round-trip: %v", id)
	}
}

// The pair must ALWAYS satisfy the table's CHECK constraints
// (owner_system_null / owner_user_set). If it can produce an inconsistent pair,
// the database discovers the mistake at the very end of provisioning instead of
// at the edge -- which is the whole reason the tier is derived here.
func TestDeriveOwner_NeverProducesAnInconsistentPair(t *testing.T) {
	for _, in := range []string{"", uuid.New().String(), "  " + uuid.New().String() + "  "} {
		kind, id, err := deriveOwner(in)
		if err != nil {
			t.Fatalf("%q: unexpected error: %v", in, err)
		}
		switch kind {
		case "system":
			if id != nil {
				t.Fatalf("%q: system with a non-NULL owner violates owner_system_null", in)
			}
		case "user":
			if id == nil {
				t.Fatalf("%q: user with a NULL owner violates owner_user_set", in)
			}
		default:
			t.Fatalf("%q: kind %q is outside the enum", in, kind)
		}
	}
}

// The nil UUID is not an owner. Accepting it wrote ('user', 00000000-...) --
// a reality owned by a user that cannot exist, satisfying every CHECK on the
// table and sitting in the partial owner index.
func TestDeriveOwner_NilUUIDIsRefused(t *testing.T) {
	_, _, err := deriveOwner(uuid.Nil.String())
	if err == nil {
		t.Fatal("the nil UUID must not be accepted as an owner")
	}
	if !strings.Contains(err.Error(), "nil UUID") {
		t.Fatalf("error should name the nil UUID, got: %v", err)
	}
}

// ...and it is REFUSED, not silently downgraded to platform-owned: an operator
// who typed an owner meant to set one.
func TestDeriveOwner_NilUUIDIsNotCoercedToSystem(t *testing.T) {
	kind, _, err := deriveOwner(uuid.Nil.String())
	if err == nil && kind == "system" {
		t.Fatal("a nil owner was silently turned into a platform-owned reality")
	}
}

func TestDeriveOwner_MalformedIsRefused(t *testing.T) {
	for _, bad := range []string{"nope", "12345", uuid.New().String() + "x"} {
		if _, _, err := deriveOwner(bad); err == nil {
			t.Fatalf("%q should be refused", bad)
		}
	}
}
