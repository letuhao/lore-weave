// Package miniostore is the minio-go implementation of object_store.Store,
// targeting the `lw-event-archive` bucket (internal cold storage; no public
// policy needed).
package miniostore

import (
	"bytes"
	"context"
	"fmt"
	"io"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

// Store wraps a minio client. Satisfies object_store.Store.
type Store struct {
	client *minio.Client
}

// Config is the constructor input.
type Config struct {
	Endpoint  string // host:port (no scheme)
	AccessKey string
	SecretKey string
	UseSSL    bool
}

// New constructs a Store + pings the endpoint by listing buckets.
func New(ctx context.Context, c Config) (*Store, error) {
	cli, err := minio.New(c.Endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(c.AccessKey, c.SecretKey, ""),
		Secure: c.UseSSL,
	})
	if err != nil {
		return nil, fmt.Errorf("miniostore: new client: %w", err)
	}
	if _, err := cli.ListBuckets(ctx); err != nil {
		return nil, fmt.Errorf("miniostore: connectivity check: %w", err)
	}
	return &Store{client: cli}, nil
}

// EnsureBucket creates the bucket if absent (idempotent).
func (s *Store) EnsureBucket(ctx context.Context, bucket string) error {
	exists, err := s.client.BucketExists(ctx, bucket)
	if err != nil {
		return fmt.Errorf("miniostore: bucket exists %s: %w", bucket, err)
	}
	if exists {
		return nil
	}
	if err := s.client.MakeBucket(ctx, bucket, minio.MakeBucketOptions{}); err != nil {
		// Tolerate a race where another worker created it between the check
		// and the make.
		if exists2, e2 := s.client.BucketExists(ctx, bucket); e2 == nil && exists2 {
			return nil
		}
		return fmt.Errorf("miniostore: make bucket %s: %w", bucket, err)
	}
	return nil
}

// Put uploads a blob.
func (s *Store) Put(ctx context.Context, bucket, key string, blob []byte) error {
	_, err := s.client.PutObject(ctx, bucket, key, bytes.NewReader(blob), int64(len(blob)),
		minio.PutObjectOptions{ContentType: "application/octet-stream"})
	if err != nil {
		return fmt.Errorf("miniostore: put %s/%s: %w", bucket, key, err)
	}
	return nil
}

// Get reads a blob back.
func (s *Store) Get(ctx context.Context, bucket, key string) ([]byte, error) {
	obj, err := s.client.GetObject(ctx, bucket, key, minio.GetObjectOptions{})
	if err != nil {
		return nil, fmt.Errorf("miniostore: get %s/%s: %w", bucket, key, err)
	}
	defer obj.Close()
	b, err := io.ReadAll(obj)
	if err != nil {
		return nil, fmt.Errorf("miniostore: read %s/%s: %w", bucket, key, err)
	}
	return b, nil
}

// Exists is a cheap HEAD (StatObject) check.
func (s *Store) Exists(ctx context.Context, bucket, key string) (bool, error) {
	_, err := s.client.StatObject(ctx, bucket, key, minio.StatObjectOptions{})
	if err != nil {
		resp := minio.ToErrorResponse(err)
		if resp.Code == "NoSuchKey" || resp.StatusCode == 404 {
			return false, nil
		}
		return false, fmt.Errorf("miniostore: stat %s/%s: %w", bucket, key, err)
	}
	return true, nil
}
