// Package storage — Phase 5e-β.2 gateway-side MinIO staging for audio_gen URL mode.
//
// The audio-cache bucket is PUBLIC-READ — mirrors book-service's
// loreweave-media pattern (set anonymous GET, object keys are UUIDs
// unguessable; URL IS the bearer token). Static URLs constructed
// against MINIO_EXTERNAL_URL — no presigned URLs to avoid the SigV4
// host-rewrite trap (/review-impl(DESIGN) HIGH#1).
//
// Lifecycle is set server-side via MinIO bucket lifecycle (1-day
// minimum; objects auto-deleted). No Go cleanup goroutine needed.
package storage

import (
	"bytes"
	"context"
	"fmt"
	"log/slog"
	"strings"

	"github.com/google/uuid"
	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
	"github.com/minio/minio-go/v7/pkg/lifecycle"
)

// AudioCache stages generated audio bytes in MinIO and returns public URLs.
type AudioCache struct {
	client      *minio.Client
	bucket      string
	externalURL string
}

// Config carries the MinIO + bucket settings.
type Config struct {
	Endpoint    string // e.g. "minio:9000" (in-cluster)
	AccessKey   string
	SecretKey   string
	UseSSL      bool
	Bucket      string // e.g. "loreweave-audio-cache"
	ExternalURL string // e.g. "http://localhost:9123" (dev) or "https://media.loreweave.com" (prod)
}

// NewAudioCache initializes the MinIO client, ensures the bucket exists,
// sets public-read policy + lifecycle. Returns nil-non-error if
// ExternalURL is empty (treat as misconfigured — URL mode unavailable
// but b64_json still works; caller checks for nil).
func NewAudioCache(ctx context.Context, cfg Config, logger *slog.Logger) (*AudioCache, error) {
	if cfg.ExternalURL == "" {
		return nil, fmt.Errorf("audio cache requires ExternalURL (MINIO_EXTERNAL_URL)")
	}
	if cfg.Endpoint == "" {
		return nil, fmt.Errorf("audio cache requires Endpoint (MINIO_ENDPOINT)")
	}
	if cfg.AccessKey == "" || cfg.SecretKey == "" {
		return nil, fmt.Errorf("audio cache requires AccessKey + SecretKey")
	}
	if cfg.Bucket == "" {
		cfg.Bucket = "loreweave-audio-cache"
	}

	mc, err := minio.New(cfg.Endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.AccessKey, cfg.SecretKey, ""),
		Secure: cfg.UseSSL,
	})
	if err != nil {
		return nil, fmt.Errorf("minio new: %w", err)
	}

	exists, err := mc.BucketExists(ctx, cfg.Bucket)
	if err != nil {
		return nil, fmt.Errorf("bucket exists check: %w", err)
	}
	if !exists {
		if mkErr := mc.MakeBucket(ctx, cfg.Bucket, minio.MakeBucketOptions{}); mkErr != nil {
			// Race: another instance may have just created it.
			if exists2, _ := mc.BucketExists(ctx, cfg.Bucket); !exists2 {
				return nil, fmt.Errorf("make bucket: %w", mkErr)
			}
		}
	}

	// Public-read policy (anonymous GET) — mirrors book-service's
	// setBucketPublicRead at media.go:587. Keys are UUIDs (unguessable).
	publicPolicy := `{
		"Version": "2012-10-17",
		"Statement": [{
			"Effect": "Allow",
			"Principal": {"AWS": ["*"]},
			"Action": ["s3:GetObject"],
			"Resource": ["arn:aws:s3:::` + cfg.Bucket + `/*"]
		}]
	}`
	if err := mc.SetBucketPolicy(ctx, cfg.Bucket, publicPolicy); err != nil {
		// /review-impl(DESIGN) MED#2 — log + continue. Bucket may already
		// have an equivalent policy; or operator can fix post-deploy.
		if logger != nil {
			logger.Warn("audio_cache: SetBucketPolicy failed — URL-mode public access may not work",
				"err", err, "bucket", cfg.Bucket)
		}
	}

	// /review-impl(DESIGN) MED#3 — local var renamed from `lifecycle` to
	// `lcCfg` to avoid shadowing the imported `lifecycle` package.
	lcCfg := lifecycle.NewConfiguration()
	lcCfg.Rules = []lifecycle.Rule{
		{
			ID:         "expire-staged-audio",
			Status:     "Enabled",
			Expiration: lifecycle.Expiration{Days: 1}, // MinIO minimum
		},
	}
	if err := mc.SetBucketLifecycle(ctx, cfg.Bucket, lcCfg); err != nil {
		// /review-impl(DESIGN) MED#2 — log + continue. Non-fatal; bucket
		// may grow if lifecycle PUT fails but URL mode still works.
		if logger != nil {
			logger.Warn("audio_cache: SetBucketLifecycle failed — bucket may grow unbounded",
				"err", err, "bucket", cfg.Bucket)
		}
	}

	return &AudioCache{
		client:      mc,
		bucket:      cfg.Bucket,
		externalURL: strings.TrimRight(cfg.ExternalURL, "/"),
	}, nil
}

// allowedAudioFormats whitelist — /review-impl(BUILD) M#4. Defends
// against path-traversal in object keys when a non-handler caller
// (cron, future RabbitMQ submit) bypasses validateAudioGenInput.
var allowedAudioFormats = map[string]bool{
	"mp3": true, "opus": true, "aac": true, "flac": true, "wav": true, "pcm": true,
}

// allowedAudioContentTypes whitelist — /review-impl(BUILD) H#5. Defends
// against an attacker-controlled BYOK provider returning
// Content-Type: text/html with audio bytes, which could yield XSS via
// the public bucket URL. We pin to the audio/* MIME set.
var allowedAudioContentTypes = map[string]bool{
	"audio/mpeg": true, "audio/mp3": true, "audio/ogg": true, "audio/opus": true,
	"audio/aac": true, "audio/flac": true, "audio/wav": true, "audio/x-wav": true,
	"audio/webm": true, "audio/mp4": true, "audio/x-pcm": true,
}

// Stage uploads audio bytes to the bucket and returns a public URL.
//
// /review-impl(DESIGN) LOW#5 — uses caller-specified `format` for the
// extension, not upstream `contentType` (which may be missing).
// /review-impl(DESIGN) MED#11 — refuses to stage zero-byte data.
// /review-impl(BUILD) H#5 — sanitizes Content-Type to an audio MIME
// whitelist (defends against attacker-BYOK XSS via mismatched MIME).
// /review-impl(BUILD) M#4 — sanitizes format to alphanumeric whitelist
// (defends against object-key path traversal).
func (a *AudioCache) Stage(ctx context.Context, jobID uuid.UUID, idx int, format string, data []byte, contentType string) (string, error) {
	if len(data) == 0 {
		return "", fmt.Errorf("audio_cache: refusing to stage 0-byte object (jobID=%s idx=%d)", jobID, idx)
	}
	if format == "" || !allowedAudioFormats[format] {
		format = "mp3"
	}
	objectKey := fmt.Sprintf("jobs/%s/%d.%s", jobID, idx, format)
	if contentType == "" || !allowedAudioContentTypes[contentType] {
		contentType = "audio/mpeg"
	}
	_, err := a.client.PutObject(ctx, a.bucket, objectKey,
		bytes.NewReader(data), int64(len(data)),
		minio.PutObjectOptions{ContentType: contentType})
	if err != nil {
		return "", fmt.Errorf("audio_cache put object: %w", err)
	}
	return fmt.Sprintf("%s/%s/%s", a.externalURL, a.bucket, objectKey), nil
}

// Bucket returns the configured bucket name (helpful for tests).
func (a *AudioCache) Bucket() string {
	return a.bucket
}
