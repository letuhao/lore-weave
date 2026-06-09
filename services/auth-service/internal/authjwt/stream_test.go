package authjwt

import (
	"testing"
	"time"

	"github.com/google/uuid"
)

func TestSignAndParseStreamTicket(t *testing.T) {
	secret := []byte("test-jwt-secret-at-least-32-characters-long")
	uid := uuid.New()
	token, err := SignStream(secret, uid, 2*time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	parsed, err := ParseUserID(secret, token)
	if err != nil {
		t.Fatal(err)
	}
	if parsed != uid {
		t.Fatalf("expected %s, got %s", uid, parsed)
	}
}
