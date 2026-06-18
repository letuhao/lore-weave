package break_glass

import (
	"errors"
	"strings"
	"testing"
	"time"
)

func ok() Request {
	return Request{
		PrimaryActor:   "ops1",
		SecondaryActor: "ops2",
		Reason:         strings.Repeat("x", 100), // exactly 100 chars
		IncidentTicket: "INC-1234",
		RequestedTTL:   24 * time.Hour,
	}
}

func TestValidate_HappyPath(t *testing.T) {
	if err := ok().Validate(); err != nil {
		t.Fatalf("ok request should validate: %v", err)
	}
}

func TestValidate_DualActorRequired(t *testing.T) {
	r := ok()
	r.SecondaryActor = "ops1"
	err := r.Validate()
	if !errors.Is(err, ErrBreakGlass) || !strings.Contains(err.Error(), "dual-actor") {
		t.Fatalf("want dual-actor failure, got %v", err)
	}
}

func TestValidate_Reason100CharsMin(t *testing.T) {
	r := ok()
	r.Reason = strings.Repeat("x", 99)
	err := r.Validate()
	if !errors.Is(err, ErrBreakGlass) {
		t.Fatalf("want ErrBreakGlass, got %v", err)
	}
	if !strings.Contains(err.Error(), ">=100") {
		t.Fatalf("want >=100 message, got %v", err)
	}
}

func TestValidate_TTLCapped(t *testing.T) {
	r := ok()
	r.RequestedTTL = 25 * time.Hour
	if err := r.Validate(); !errors.Is(err, ErrBreakGlass) {
		t.Fatalf("want TTL cap failure, got %v", err)
	}
}

func TestValidate_IncidentTicketRequired(t *testing.T) {
	r := ok()
	r.IncidentTicket = ""
	if err := r.Validate(); !errors.Is(err, ErrBreakGlass) {
		t.Fatalf("want ticket required, got %v", err)
	}
}
