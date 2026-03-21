package config

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

type Config struct {
	HTTPAddr              string
	DatabaseURL           string
	JWTSecret             string
	AccessTokenTTL        time.Duration
	RefreshTokenTTL       time.Duration
	PasswordMinLength     int
	RateLimitWindow       time.Duration
	RateLimitMax          int
	DevLogEmailTokens     bool
}

func Load() (*Config, error) {
	c := &Config{
		HTTPAddr:          getEnv("HTTP_ADDR", ":8081"),
		DatabaseURL:       os.Getenv("DATABASE_URL"),
		JWTSecret:         os.Getenv("JWT_SECRET"),
		PasswordMinLength: getInt("PASSWORD_MIN_LENGTH", 8),
		RateLimitMax:      getInt("RATE_LIMIT_MAX_REQUESTS", 60),
		DevLogEmailTokens: getBool("DEV_LOG_EMAIL_TOKENS", true),
	}
	if c.DatabaseURL == "" {
		return nil, fmt.Errorf("DATABASE_URL is required")
	}
	if len(c.JWTSecret) < 32 {
		return nil, fmt.Errorf("JWT_SECRET must be at least 32 characters")
	}
	accSec := getInt("ACCESS_TOKEN_TTL_SECONDS", 900)
	refSec := getInt("REFRESH_TOKEN_TTL_SECONDS", 60*60*24*7)
	c.AccessTokenTTL = time.Duration(accSec) * time.Second
	c.RefreshTokenTTL = time.Duration(refSec) * time.Second
	rlWin := getInt("RATE_LIMIT_WINDOW_SECONDS", 60)
	c.RateLimitWindow = time.Duration(rlWin) * time.Second
	return c, nil
}

func getEnv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func getInt(k string, def int) int {
	v := os.Getenv(k)
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return def
	}
	return n
}

func getBool(k string, def bool) bool {
	v := os.Getenv(k)
	if v == "" {
		return def
	}
	b, err := strconv.ParseBool(v)
	if err != nil {
		return def
	}
	return b
}
