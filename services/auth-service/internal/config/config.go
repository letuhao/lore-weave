package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
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
	// Optional SMTP (e.g. Mailhog: host localhost, port 1025). If SMTPHost is empty, no email is sent.
	SMTPHost     string
	SMTPPort     int
	SMTPUser     string
	SMTPPassword string
	SMTPFrom     string
	// Browser base URL for links in emails (e.g. http://localhost:5173).
	PublicAppURL string
	// Notification service internal URL for creating notifications on events.
	NotificationServiceInternalURL string
	InternalServiceToken           string
}

func Load() (*Config, error) {
	c := &Config{
		HTTPAddr:          getEnv("HTTP_ADDR", ":8081"),
		DatabaseURL:       os.Getenv("DATABASE_URL"),
		JWTSecret:         os.Getenv("JWT_SECRET"),
		PasswordMinLength: getInt("PASSWORD_MIN_LENGTH", 8),
		RateLimitMax:      getInt("RATE_LIMIT_MAX_REQUESTS", 60),
		DevLogEmailTokens: getBool("DEV_LOG_EMAIL_TOKENS", true),
		SMTPHost:          os.Getenv("SMTP_HOST"),
		SMTPPort:          getInt("SMTP_PORT", 1025),
		SMTPUser:          os.Getenv("SMTP_USER"),
		SMTPPassword:      os.Getenv("SMTP_PASSWORD"),
		SMTPFrom:          getEnv("SMTP_FROM", ""),
		PublicAppURL:                   getEnv("PUBLIC_APP_URL", ""),
		NotificationServiceInternalURL: getEnv("NOTIFICATION_SERVICE_INTERNAL_URL", ""),
		InternalServiceToken:           os.Getenv("INTERNAL_SERVICE_TOKEN"),
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
	if c.SMTPHost != "" && strings.TrimSpace(c.SMTPFrom) == "" {
		return nil, fmt.Errorf("SMTP_FROM is required when SMTP_HOST is set")
	}
	if c.InternalServiceToken == "" {
		return nil, fmt.Errorf("INTERNAL_SERVICE_TOKEN is required")
	}
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
