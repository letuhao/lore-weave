package piikms

// KMS-gated live-smoke against a REAL KMS (LocalStack in dev). Gated on
// PIIKMS_TEST_KMS_ENDPOINT (skips in the normal job). Proves the AWS-SDK wiring
// the in-process fake cannot: real GenerateDataKey/Decrypt round-trip. Symmetric
// KMS is faithful on LocalStack-community (unlike asymmetric Sign — see 094).

import (
	"bytes"
	"context"
	"os"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	awskms "github.com/aws/aws-sdk-go-v2/service/kms"
	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/meta"
)

func TestLive_RealKMSRoundTrip(t *testing.T) {
	ep := os.Getenv("PIIKMS_TEST_KMS_ENDPOINT")
	if ep == "" {
		t.Skip("PIIKMS_TEST_KMS_ENDPOINT not set; skipping real-KMS live-smoke")
	}
	ctx := context.Background()
	cfg, err := awsconfig.LoadDefaultConfig(ctx,
		awsconfig.WithRegion("us-east-1"),
		awsconfig.WithCredentialsProvider(credentials.NewStaticCredentialsProvider("test", "test", "")),
	)
	if err != nil {
		t.Fatalf("aws config: %v", err)
	}
	cl := awskms.NewFromConfig(cfg, func(o *awskms.Options) { o.BaseEndpoint = aws.String(ep) })

	ck, err := cl.CreateKey(ctx, &awskms.CreateKeyInput{}) // symmetric ENCRYPT_DECRYPT default
	if err != nil {
		t.Fatalf("CreateKey: %v", err)
	}
	keyRef := "aws-kms:" + *ck.KeyMetadata.KeyId

	c := NewAWSKMSClient(cl)
	kek, keyMaterial, err := c.ProvisionKEK(ctx, keyRef)
	if err != nil {
		t.Fatalf("ProvisionKEK (real KMS): %v", err)
	}
	payload := []byte(`{"legal_name":"Carol","email":"carol@example.com"}`)
	aad := meta.PIIAAD(uuid.New(), uuid.New())
	env, err := c.Encrypt(kek, payload, aad)
	if err != nil {
		t.Fatalf("Encrypt: %v", err)
	}
	out, err := c.Decrypt(ctx, meta.DecryptInput{
		KMSKeyRef: keyRef, KeyMaterial: keyMaterial, Ciphertext: env, AAD: aad,
	})
	if err != nil {
		t.Fatalf("Decrypt (real KMS): %v", err)
	}
	if !bytes.Equal(out.Plaintext, payload) {
		t.Fatalf("real-KMS round-trip mismatch: %q", out.Plaintext)
	}
	// Forensic correlation: the KMS request id must be threaded back (the
	// CloudTrail join key). Only a REAL KMS populates response metadata.
	if out.KMSRequestID == "" {
		t.Error("KMSRequestID not populated from real KMS response metadata")
	}
}
