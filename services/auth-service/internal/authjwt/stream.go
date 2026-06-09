package authjwt

import (
	"fmt"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
)

const StreamTokenType = "stream"

type StreamClaims struct {
	Type string `json:"typ"`
	jwt.RegisteredClaims
}

func SignStream(secret []byte, userID uuid.UUID, ttl time.Duration) (string, error) {
	now := time.Now()
	claims := StreamClaims{
		Type: StreamTokenType,
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   userID.String(),
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(now.Add(ttl)),
		},
	}
	t := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return t.SignedString(secret)
}

// ParseUserID accepts a short-lived stream ticket or a normal access token.
func ParseUserID(secret []byte, tokenStr string) (uuid.UUID, error) {
	stream, err := jwt.ParseWithClaims(tokenStr, &StreamClaims{}, func(t *jwt.Token) (interface{}, error) {
		if t.Method != jwt.SigningMethodHS256 {
			return nil, fmt.Errorf("unexpected signing method")
		}
		return secret, nil
	})
	if err == nil {
		if claims, ok := stream.Claims.(*StreamClaims); ok && stream.Valid {
			if claims.Type == StreamTokenType {
				return uuid.Parse(claims.Subject)
			}
		}
	}
	access, err := ParseAccess(secret, tokenStr)
	if err != nil {
		return uuid.Nil, err
	}
	return uuid.Parse(access.Subject)
}
