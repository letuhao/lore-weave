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

	// WS-1.0 (DECISIONS-SEALED PO-2) — the deployment KEK that WRAPS each user's DEK.
	// auth-service stores only the wrapped blob; it never sees a user's content.
	// Unset => GET /internal/users/{id}/dek fails CLOSED (503) rather than letting a
	// deployment silently store diaries, assistant chat and facts in the clear.
	DiaryEncryptionKey string

	// Public MCP human-approval execute (P4 / OD-2): base URLs of the domain
	// services whose POST /v1/<domain>/actions/confirm the approve handler replays
	// an approved confirm token to, KEYED by the propose result's `domain`. Only a
	// configured domain is executable; an approval whose domain has no URL fails
	// closed (the row is recorded but Approve returns a clear "not executable").
	DomainConfirmServiceURLs map[string]string

	// Q-GATE (public MCP): key creation is gated by this platform feature flag — any
	// user may mint a public MCP key when ON, fast kill-switch when OFF. Default OFF.
	PublicMcpEnabled bool

	// Admin-JWT issuance (074/075). Feature is ENABLED iff KMSAdminSigningKeyID
	// is set; when enabled the other admin fields are required (fail-closed).
	AdminIssuanceEnabled   bool
	KMSAdminSigningKeyID   string        // AWS KMS asymmetric (RSA SIGN_VERIFY) key id/arn
	KMSEndpoint            string        // override KMS endpoint (e.g. LocalStack http://localhost:54566)
	AWSRegion              string        // AWS region for the KMS client
	AdminTokenIssuerSecret string        // X-Internal-Token required to mint admin tokens; DISTINCT from InternalServiceToken
	AdminAuditHMACKey      string        // HMAC key for break-glass reason hashing (never store raw reason)
	AdminTokenTTL          time.Duration // TTL for normal admin tokens (default 15m)
	// AdminJWTLocalPrivateKeyPEM is a DEV/SELF-HOSTED fallback signer: an RSA
	// private key (PKCS#8 or PKCS#1 PEM) used to sign admin JWTs in-process when no
	// KMS key is configured. PRODUCTION SHOULD USE KMS (key never leaves KMS); this
	// exists so the admin CMS works on a local/self-hosted stack without AWS. KMS
	// wins when both are set. The matching PUBLIC key goes to verifiers (glossary's
	// ADMIN_JWT_PUBLIC_KEY_PEM).
	AdminJWTLocalPrivateKeyPEM string

	// P5 public-MCP OAuth 2.1. Reuses the admin RS256 signer to mint access tokens
	// with a DISTINCT issuer + audience (never an admin token). Enabled iff admin
	// issuance is on (a signer exists) AND the public MCP feature flag is on.
	OAuthEnabled    bool
	OAuthIssuer     string        // "iss" of OAuth access tokens (MUST differ from the admin issuer)
	OAuthResource   string        // canonical MCP resource URL = the "aud" (RFC 8707); MUST equal the edge's MCP_RESOURCE_URL
	OAuthAccessTTL  time.Duration // OAuth access-token TTL (default 10m)
	OAuthDefaultRPM int           // default per-grant rate limit advertised to the edge
	OAuthCodeTTL    time.Duration // authorization-code TTL (default 60s, single-use)
	OAuthRefreshTTL time.Duration // OAuth refresh-token TTL (default 30d)
	OAuthConsentURL string        // FE consent page URL the authorize endpoint redirects to (default "${PublicAppURL}/oauth/consent")
	// P5 slice 3 — open Dynamic Client Registration (RFC 7591). The /oauth/register
	// endpoint is public+unauthenticated; this flag is its kill-switch (default ON when
	// OAuth is enabled, per the locked PO "open DCR" decision) and the per-IP rate cap.
	OAuthDCREnabled     bool
	OAuthDCRRatePerHour int // per-IP /oauth/register cap; 0 = UNLIMITED (use OAUTH_DCR_ENABLED=false to disable)
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
		DiaryEncryptionKey:             os.Getenv("DIARY_ENCRYPTION_KEY"),
		PublicMcpEnabled:               getBool("PUBLIC_MCP_ENABLED", false),
		KMSAdminSigningKeyID:           os.Getenv("KMS_ADMIN_SIGNING_KEY_ID"),
		KMSEndpoint:                    os.Getenv("KMS_ENDPOINT"),
		AWSRegion:                      getEnv("AWS_REGION", "us-east-1"),
		AdminTokenIssuerSecret:         os.Getenv("ADMIN_TOKEN_ISSUER_SECRET"),
		AdminAuditHMACKey:              os.Getenv("ADMIN_AUDIT_HMAC_KEY"),
		AdminJWTLocalPrivateKeyPEM:     os.Getenv("ADMIN_JWT_LOCAL_PRIVATE_KEY_PEM"),
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
	// DIARY_ENCRYPTION_KEY may be empty — a deployment that stores no private content, in
	// which case the DEK read fails closed at REQUEST time (503), never at boot. But when it
	// IS set it is the ENTIRE confidentiality boundary for diary/assistant/facts, so hold it
	// to the same bar as JWT_SECRET: ≥32 chars, and never the SAME value as JWT_SECRET (a
	// shared secret means one leak breaks both auth and content-at-rest). Mirrors the
	// admin-secret distinctness guard below. (Review WS-2.7 finding-6.)
	if c.DiaryEncryptionKey != "" {
		if len(c.DiaryEncryptionKey) < 32 {
			return nil, fmt.Errorf("DIARY_ENCRYPTION_KEY must be at least 32 characters when set")
		}
		if c.DiaryEncryptionKey == c.JWTSecret {
			return nil, fmt.Errorf("DIARY_ENCRYPTION_KEY must differ from JWT_SECRET (separate confidentiality boundary)")
		}
	}
	c.DomainConfirmServiceURLs = loadDomainConfirmURLs()

	// Admin-JWT issuance (074/075). Feature is off unless a KMS signing key is
	// configured; when on, the rest is required and fails closed.
	c.AdminTokenTTL = time.Duration(getInt("ADMIN_TOKEN_TTL_SECONDS", 900)) * time.Second
	// Enabled by EITHER a KMS key (prod) or a local private key (dev/self-hosted).
	// KMS takes precedence at signer-construction time (main.go).
	c.AdminIssuanceEnabled = c.KMSAdminSigningKeyID != "" || c.AdminJWTLocalPrivateKeyPEM != ""
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

	// P5 OAuth 2.1: reuses the admin signer; on only when a signer exists AND the
	// public MCP flag is set. Audience-bound tokens (RFC 8707) — OAuthResource is the
	// canonical MCP URL the edge also configures as its aud.
	c.OAuthIssuer = getEnv("OAUTH_ISSUER", "loreweave-mcp-oauth")
	c.OAuthResource = getEnv("OAUTH_RESOURCE", defaultOAuthResource(c.PublicAppURL))
	c.OAuthAccessTTL = time.Duration(getInt("OAUTH_ACCESS_TTL_SECONDS", 600)) * time.Second
	c.OAuthDefaultRPM = getInt("OAUTH_DEFAULT_RPM", 60)
	c.OAuthCodeTTL = time.Duration(getInt("OAUTH_CODE_TTL_SECONDS", 60)) * time.Second
	c.OAuthRefreshTTL = time.Duration(getInt("OAUTH_REFRESH_TTL_SECONDS", 60*60*24*30)) * time.Second
	c.OAuthConsentURL = getEnv("OAUTH_CONSENT_URL", defaultConsentURL(c.PublicAppURL))
	c.OAuthDCREnabled = getBool("OAUTH_DCR_ENABLED", true)
	c.OAuthDCRRatePerHour = getInt("OAUTH_DCR_RATE_PER_HOUR", 10)
	c.OAuthEnabled = c.AdminIssuanceEnabled && c.PublicMcpEnabled
	if c.OAuthEnabled {
		if c.OAuthResource == "" {
			return nil, fmt.Errorf("OAUTH_RESOURCE (or PUBLIC_APP_URL) is required when OAuth is enabled")
		}
		// Hard separation from the admin token (defense-in-depth on top of the audience
		// split): an OAuth token must never share the admin issuer.
		if c.OAuthIssuer == "" || c.OAuthIssuer == adminTokenIssuer {
			return nil, fmt.Errorf("OAUTH_ISSUER must be set and differ from the admin issuer %q", adminTokenIssuer)
		}
		if c.OAuthAccessTTL <= 0 {
			return nil, fmt.Errorf("OAUTH_ACCESS_TTL_SECONDS must be > 0")
		}
	}
	return c, nil
}

// adminTokenIssuer mirrors contracts/adminjwt.Issuer without importing it into the
// config package (config stays dependency-light). Kept in sync by the cross-rejection
// test in the api package, which uses the real adminjwt constant.
const adminTokenIssuer = "loreweave-auth"

// defaultOAuthResource derives the canonical MCP resource URL (the OAuth audience)
// from the public app URL: "<app>/mcp". Empty when no app URL is configured.
func defaultOAuthResource(appURL string) string {
	if strings.TrimSpace(appURL) == "" {
		return ""
	}
	return strings.TrimRight(appURL, "/") + "/mcp"
}

// defaultConsentURL is the FE consent page the authorize endpoint redirects a
// logged-in user to: "<app>/oauth/consent". Empty when no app URL is configured.
func defaultConsentURL(appURL string) string {
	if strings.TrimSpace(appURL) == "" {
		return ""
	}
	return strings.TrimRight(appURL, "/") + "/oauth/consent"
}

// loadDomainConfirmURLs maps a confirm `domain` (as it appears in a propose result
// and in the /v1/<domain>/actions/confirm path) to its owning service's base URL,
// read from per-service env vars. Absent vars simply leave that domain non-executable.
func loadDomainConfirmURLs() map[string]string {
	src := map[string]string{
		"book":        "BOOK_SERVICE_URL",
		"composition": "COMPOSITION_SERVICE_URL",
		"translation": "TRANSLATION_SERVICE_URL",
		"glossary":    "GLOSSARY_SERVICE_URL",
		"kg":          "KNOWLEDGE_SERVICE_URL",
		"settings":    "PROVIDER_REGISTRY_SERVICE_URL",
	}
	out := map[string]string{}
	for domain, env := range src {
		if v := strings.TrimSpace(os.Getenv(env)); v != "" {
			out[domain] = strings.TrimRight(v, "/")
		}
	}
	return out
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
