// Package miniofetch is admin-cli's own minimal minio-go read wrapper for fetching
// archived blobs (it implements commands.ArchiveBlobFetcher structurally). It is
// deliberately self-contained — NOT a dependency on services/archive-worker: the repo
// pattern is that each service owns its object-store client (book-service,
// provider-registry, archive-worker each have their own). See D4 in
// docs/plans/2026-06-01-admin-readcmd-batch.md.
package miniofetch

import (
	"context"
	"fmt"
	"io"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

// Config is the constructor input (mirrors the archive-worker miniostore config +
// the MINIO_* env names used by archive-restore).
type Config struct {
	Endpoint  string // host:port (no scheme)
	AccessKey string
	SecretKey string
	UseSSL    bool
}

// Store is a read-only minio client wrapper.
type Store struct {
	client *minio.Client
}

// New constructs a Store and verifies connectivity by listing buckets.
func New(ctx context.Context, c Config) (*Store, error) {
	cli, err := minio.New(c.Endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(c.AccessKey, c.SecretKey, ""),
		Secure: c.UseSSL,
	})
	if err != nil {
		return nil, fmt.Errorf("miniofetch: new client: %w", err)
	}
	if _, err := cli.ListBuckets(ctx); err != nil {
		return nil, fmt.Errorf("miniofetch: connectivity check: %w", err)
	}
	return &Store{client: cli}, nil
}

// Fetch reads a blob by (bucket, key).
func (s *Store) Fetch(ctx context.Context, bucket, key string) ([]byte, error) {
	obj, err := s.client.GetObject(ctx, bucket, key, minio.GetObjectOptions{})
	if err != nil {
		return nil, fmt.Errorf("miniofetch: get %s/%s: %w", bucket, key, err)
	}
	defer obj.Close()
	b, err := io.ReadAll(obj)
	if err != nil {
		return nil, fmt.Errorf("miniofetch: read %s/%s: %w", bucket, key, err)
	}
	return b, nil
}
