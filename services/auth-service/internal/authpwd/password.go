package authpwd

import (
	"crypto/rand"
	"encoding/base64"
	"strings"

	"golang.org/x/crypto/argon2"
)

const (
	saltLen  = 16
	timeCost = 3
	memKiB   = 64 * 1024
	threads  = 4
	keyLen   = 32
)

func Hash(password string) (string, error) {
	salt := make([]byte, saltLen)
	if _, err := rand.Read(salt); err != nil {
		return "", err
	}
	hash := argon2.IDKey([]byte(password), salt, timeCost, memKiB, threads, keyLen)
	enc := base64.RawStdEncoding.EncodeToString(append(salt, hash...))
	return "argon2id$" + enc, nil
}

func Verify(password, encoded string) (bool, error) {
	const pfx = "argon2id$"
	if !strings.HasPrefix(encoded, pfx) {
		return false, nil
	}
	raw := strings.TrimPrefix(encoded, pfx)
	b, err := base64.RawStdEncoding.DecodeString(raw)
	if err != nil || len(b) < saltLen+keyLen {
		return false, nil
	}
	salt := b[:saltLen]
	want := b[saltLen : saltLen+keyLen]
	got := argon2.IDKey([]byte(password), salt, timeCost, memKiB, threads, keyLen)
	if len(got) != len(want) {
		return false, nil
	}
	var diff byte
	for i := range want {
		diff |= got[i] ^ want[i]
	}
	return diff == 0, nil
}
