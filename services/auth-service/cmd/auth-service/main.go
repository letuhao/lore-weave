package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	awskms "github.com/aws/aws-sdk-go-v2/service/kms"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/observability"

	"github.com/loreweave/auth-service/internal/adminprincipal"
	"github.com/loreweave/auth-service/internal/api"
	"github.com/loreweave/auth-service/internal/authjwt"
	"github.com/loreweave/auth-service/internal/config"
	"github.com/loreweave/auth-service/internal/migrate"
)

func main() {
	// P2·A1 — shared JSON slog logger that injects otel_trace_id from the active
	// span on ctx-carrying log calls (slog.*Context). Replaces the bare SetDefault.
	observability.SetupLogging("auth-service")

	cfg, err := config.Load()
	if err != nil {
		slog.Error("config failed", "error", err)
		os.Exit(1)
	}

	// Phase 6c — OpenTelemetry tracing. No-op when OTEL_EXPORTER_OTLP_ENDPOINT
	// is unset, so a broker-less / collector-less dev run still boots.
	shutdownTracer, err := observability.InitTracer(context.Background(), "auth-service")
	if err != nil {
		slog.Error("tracer init", "error", err)
		os.Exit(1)
	}
	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = shutdownTracer(ctx)
	}()

	ctx := context.Background()
	poolCfg, err := pgxpool.ParseConfig(cfg.DatabaseURL)
	if err != nil {
		slog.Error("db config parse failed", "error", err)
		os.Exit(1)
	}
	if poolCfg.MaxConns == 0 || poolCfg.MaxConns == 4 { // 4 is pgx default
		poolCfg.MaxConns = 10
	}
	if poolCfg.MinConns == 0 {
		poolCfg.MinConns = 2
	}
	if poolCfg.MaxConnLifetime == 0 {
		poolCfg.MaxConnLifetime = 30 * time.Minute
	}
	if poolCfg.MaxConnIdleTime == 0 {
		poolCfg.MaxConnIdleTime = 5 * time.Minute
	}
	pool, err := pgxpool.NewWithConfig(ctx, poolCfg)
	if err != nil {
		slog.Error("db connect failed", "error", err)
		os.Exit(1)
	}
	defer pool.Close()
	if err := migrate.Up(ctx, pool); err != nil {
		slog.Error("migrate failed", "error", err)
		os.Exit(1)
	}
	srv := api.NewServer(pool, cfg)

	// Admin-JWT issuance (074/075). Build the KMS-backed signer (the RSA private
	// key never leaves KMS) and enable the endpoints. Fails closed at startup if
	// the KMS key is unreachable or not RSA (NewKMSSigner does a GetPublicKey).
	if cfg.AdminIssuanceEnabled {
		var signer authjwt.DigestSigner
		if cfg.KMSAdminSigningKeyID != "" {
			// Production path: KMS-backed signer; RSA private key never leaves KMS.
			awsCfg, err := awsconfig.LoadDefaultConfig(ctx, awsconfig.WithRegion(cfg.AWSRegion))
			if err != nil {
				slog.Error("aws config load failed", "error", err)
				os.Exit(1)
			}
			kmsClient := awskms.NewFromConfig(awsCfg, func(o *awskms.Options) {
				if cfg.KMSEndpoint != "" {
					o.BaseEndpoint = &cfg.KMSEndpoint
				}
			})
			ks, err := authjwt.NewKMSSigner(ctx, kmsClient, cfg.KMSAdminSigningKeyID)
			if err != nil {
				slog.Error("admin KMS signer init failed", "error", err)
				os.Exit(1)
			}
			signer = ks
		} else {
			// DEV / self-hosted path: in-process RSA key from config. Loud warning —
			// the private key lives in the process, not KMS.
			ls, err := authjwt.NewLocalKeySigner([]byte(cfg.AdminJWTLocalPrivateKeyPEM))
			if err != nil {
				slog.Error("admin local signer init failed", "error", err)
				os.Exit(1)
			}
			signer = ls
			slog.Warn("admin-JWT issuance using a LOCAL in-process signing key (dev/self-hosted) — production should use KMS")
		}
		srv.EnableAdminIssuance(signer, adminprincipal.New(pool), cfg.AdminTokenIssuerSecret, cfg.AdminAuditHMACKey, cfg.AdminTokenTTL)
		slog.Info("admin-JWT issuance enabled", "kid", signer.KID())

		// P5 public-MCP OAuth 2.1 (slice 1): reuse the SAME RS256 signer to mint
		// audience-bound access tokens with a DISTINCT issuer; the edge verifies them
		// via /oauth/jwks. On only when the public MCP flag is also set.
		if cfg.OAuthEnabled {
			srv.EnableOAuth(signer, api.OAuthOptions{
				Issuer:         cfg.OAuthIssuer,
				Resource:       cfg.OAuthResource,
				AccessTTL:      cfg.OAuthAccessTTL,
				DefaultRPM:     cfg.OAuthDefaultRPM,
				CodeTTL:        cfg.OAuthCodeTTL,
				RefreshTTL:     cfg.OAuthRefreshTTL,
				ConsentURL:     cfg.OAuthConsentURL,
				DCREnabled:     cfg.OAuthDCREnabled,
				DCRRatePerHour: cfg.OAuthDCRRatePerHour,
			})
			slog.Info("public-MCP OAuth enabled", "issuer", cfg.OAuthIssuer, "resource", cfg.OAuthResource, "kid", signer.KID(), "dcr", cfg.OAuthDCREnabled)
		}
	}

	httpSrv := &http.Server{
		Addr:              cfg.HTTPAddr,
		Handler:           srv.Router(),
		ReadHeaderTimeout: 10 * time.Second,
	}
	go func() {
		slog.Info("listening", "addr", cfg.HTTPAddr)
		if err := httpSrv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("listen failed", "error", err)
			os.Exit(1)
		}
	}()
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if err := httpSrv.Shutdown(shutdownCtx); err != nil {
		slog.Error("shutdown error", "error", err)
	}
}
