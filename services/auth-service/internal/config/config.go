package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	HTTPAddr          string
	DatabaseURL       string
	JWTSecret         string
	AccessTokenTTL    time.Duration
	RefreshTokenTTL   time.Duration
	PasswordMinLength int
	RateLimitWindow   time.Duration
	RateLimitMax      int
	DevLogEmailTokens bool
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

	// Admin-JWT issuance (074/075). Feature is ENABLED iff KMSAdminSigningKeyID
	// is set; when enabled the other admin fields are required (fail-closed).
	AdminIssuanceEnabled   bool
	KMSAdminSigningKeyID   string        // AWS KMS asymmetric (RSA SIGN_VERIFY) key id/arn
	KMSEndpoint            string        // override KMS endpoint (e.g. LocalStack http://localhost:54566)
	AWSRegion              string        // AWS region for the KMS client
	AdminTokenIssuerSecret string        // X-Internal-Token required to mint admin tokens; DISTINCT from InternalServiceToken
	AdminAuditHMACKey      string        // HMAC key for break-glass reason hashing (never store raw reason)
	AdminTokenTTL          time.Duration // TTL for normal admin tokens (default 15m)
}

func Load() (*Config, error) {
	c := &Config{
		HTTPAddr:                       getEnv("HTTP_ADDR", ":8081"),
		DatabaseURL:                    os.Getenv("DATABASE_URL"),
		JWTSecret:                      os.Getenv("JWT_SECRET"),
		PasswordMinLength:              getInt("PASSWORD_MIN_LENGTH", 8),
		RateLimitMax:                   getInt("RATE_LIMIT_MAX_REQUESTS", 60),
		DevLogEmailTokens:              getBool("DEV_LOG_EMAIL_TOKENS", true),
		SMTPHost:                       os.Getenv("SMTP_HOST"),
		SMTPPort:                       getInt("SMTP_PORT", 1025),
		SMTPUser:                       os.Getenv("SMTP_USER"),
		SMTPPassword:                   os.Getenv("SMTP_PASSWORD"),
		SMTPFrom:                       getEnv("SMTP_FROM", ""),
		PublicAppURL:                   getEnv("PUBLIC_APP_URL", ""),
		NotificationServiceInternalURL: getEnv("NOTIFICATION_SERVICE_INTERNAL_URL", ""),
		InternalServiceToken:           os.Getenv("INTERNAL_SERVICE_TOKEN"),
		KMSAdminSigningKeyID:           os.Getenv("KMS_ADMIN_SIGNING_KEY_ID"),
		KMSEndpoint:                    os.Getenv("KMS_ENDPOINT"),
		AWSRegion:                      getEnv("AWS_REGION", "us-east-1"),
		AdminTokenIssuerSecret:         os.Getenv("ADMIN_TOKEN_ISSUER_SECRET"),
		AdminAuditHMACKey:              os.Getenv("ADMIN_AUDIT_HMAC_KEY"),
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

	// Admin-JWT issuance (074/075). Feature is off unless a KMS signing key is
	// configured; when on, the rest is required and fails closed.
	c.AdminTokenTTL = time.Duration(getInt("ADMIN_TOKEN_TTL_SECONDS", 900)) * time.Second
	c.AdminIssuanceEnabled = c.KMSAdminSigningKeyID != ""
	if c.AdminIssuanceEnabled {
		if len(c.AdminTokenIssuerSecret) < 32 {
			return nil, fmt.Errorf("ADMIN_TOKEN_ISSUER_SECRET must be >=32 chars when admin issuance is enabled")
		}
		if c.AdminTokenIssuerSecret == c.InternalServiceToken {
			return nil, fmt.Errorf("ADMIN_TOKEN_ISSUER_SECRET must differ from INTERNAL_SERVICE_TOKEN (separate privilege)")
		}
		if len(c.AdminAuditHMACKey) < 32 {
			return nil, fmt.Errorf("ADMIN_AUDIT_HMAC_KEY must be >=32 chars when admin issuance is enabled")
		}
		if c.AdminTokenTTL <= 0 {
			return nil, fmt.Errorf("ADMIN_TOKEN_TTL_SECONDS must be > 0")
		}
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
