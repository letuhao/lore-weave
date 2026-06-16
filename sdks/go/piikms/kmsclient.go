package piikms

import (
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"errors"
	"fmt"
	"strings"

	awsmiddleware "github.com/aws/aws-sdk-go-v2/aws/middleware"
	awskms "github.com/aws/aws-sdk-go-v2/service/kms"
	kmstypes "github.com/aws/aws-sdk-go-v2/service/kms/types"

	"github.com/loreweave/foundation/contracts/meta"
)

const (
	envelopeVersion byte = 1
	nonceLen             = 12 // AES-GCM standard 96-bit nonce
	kekLen               = 32 // AES-256 key
	providerPrefix       = "aws-kms:"
)

// kmsAPI is the minimal AWS KMS surface the adapter needs (so tests inject a
// faithful in-process fake). *awskms.Client satisfies it.
type kmsAPI interface {
	GenerateDataKey(ctx context.Context, in *awskms.GenerateDataKeyInput, optFns ...func(*awskms.Options)) (*awskms.GenerateDataKeyOutput, error)
	Decrypt(ctx context.Context, in *awskms.DecryptInput, optFns ...func(*awskms.Options)) (*awskms.DecryptOutput, error)
	ScheduleKeyDeletion(ctx context.Context, in *awskms.ScheduleKeyDeletionInput, optFns ...func(*awskms.Options)) (*awskms.ScheduleKeyDeletionOutput, error)
}

// AWSKMSClient implements meta.KMSClient (Decrypt) + the encrypt/provision
// helpers, backed by AWS KMS.
type AWSKMSClient struct {
	kms kmsAPI
}

// NewAWSKMSClient wraps a KMS API (production: *awskms.Client; tests: a fake).
func NewAWSKMSClient(api kmsAPI) *AWSKMSClient { return &AWSKMSClient{kms: api} }

// arn strips the "<provider>:" prefix off a pii_kek.kms_key_ref to get the bare
// KMS KeyId. Only the aws-kms provider is supported here; anything else is a
// configuration error (fail-closed).
func arn(kmsKeyRef string) (string, error) {
	if !strings.HasPrefix(kmsKeyRef, providerPrefix) {
		return "", fmt.Errorf("piikms: kms_key_ref %q is not an %q reference", kmsKeyRef, providerPrefix)
	}
	id := strings.TrimPrefix(kmsKeyRef, providerPrefix)
	if id == "" {
		return "", fmt.Errorf("piikms: empty KMS key id after provider prefix")
	}
	return id, nil
}

// ProvisionKEK mints a fresh per-user KEK via KMS GenerateDataKey under the
// per-user CMK. Returns the plaintext KEK (for an immediate Encrypt — the
// caller MUST zeroize it after use) and the wrapped key_material to persist in
// pii_kek.
func (c *AWSKMSClient) ProvisionKEK(ctx context.Context, kmsKeyRef string) (plaintextKEK, keyMaterial []byte, err error) {
	keyID, err := arn(kmsKeyRef)
	if err != nil {
		return nil, nil, err
	}
	out, err := c.kms.GenerateDataKey(ctx, &awskms.GenerateDataKeyInput{
		KeyId:   &keyID,
		KeySpec: kmstypes.DataKeySpecAes256,
	})
	if err != nil {
		return nil, nil, fmt.Errorf("piikms: GenerateDataKey: %w", mapKMSErr(err))
	}
	if len(out.Plaintext) != kekLen {
		return nil, nil, fmt.Errorf("piikms: KMS returned %d-byte KEK, want %d", len(out.Plaintext), kekLen)
	}
	return out.Plaintext, out.CiphertextBlob, nil
}

// Encrypt seals plaintext under the (already-unwrapped) plaintext KEK using
// AES-256-GCM with a FRESH random 96-bit nonce, and returns the payload
// envelope [version|nonce|ct‖tag]. Pure crypto — no KMS call. The caller owns
// plaintextKEK and SHOULD zeroize it after the encrypt batch.
func (c *AWSKMSClient) Encrypt(plaintextKEK, plaintext, aad []byte) ([]byte, error) {
	gcm, err := newGCM(plaintextKEK)
	if err != nil {
		return nil, err
	}
	nonce := make([]byte, nonceLen)
	if _, err := rand.Read(nonce); err != nil {
		return nil, fmt.Errorf("piikms: nonce rand: %w", err) // fail-closed on short read
	}
	// Bind the envelope version into the AEAD AAD so a future v2 cannot be
	// downgraded by flipping the (otherwise unauthenticated) version byte.
	ct := gcm.Seal(nil, nonce, plaintext, versionedAAD(envelopeVersion, aad))
	env := make([]byte, 0, 1+nonceLen+len(ct))
	env = append(env, envelopeVersion)
	env = append(env, nonce...)
	env = append(env, ct...)
	return env, nil
}

// Decrypt implements meta.KMSClient: KMS-decrypt the wrapped KEK (in.KeyMaterial)
// under the per-user CMK (in.KMSKeyRef), then AES-256-GCM open the payload
// envelope (in.Ciphertext) with the KEK + in.AAD. The plaintext KEK is zeroized
// before return.
func (c *AWSKMSClient) Decrypt(ctx context.Context, in meta.DecryptInput) (meta.DecryptOutput, error) {
	if len(in.KeyMaterial) == 0 {
		return meta.DecryptOutput{}, fmt.Errorf("piikms: empty KeyMaterial (wrapped KEK)")
	}
	keyID, err := arn(in.KMSKeyRef)
	if err != nil {
		return meta.DecryptOutput{}, err
	}
	out, err := c.kms.Decrypt(ctx, &awskms.DecryptInput{
		CiphertextBlob: in.KeyMaterial,
		KeyId:          &keyID,
	})
	if err != nil {
		return meta.DecryptOutput{}, mapKMSErr(err)
	}
	kek := out.Plaintext
	defer zeroize(kek)
	if len(kek) != kekLen {
		return meta.DecryptOutput{}, fmt.Errorf("piikms: unwrapped KEK is %d bytes, want %d", len(kek), kekLen)
	}
	plaintext, err := openEnvelope(kek, in.Ciphertext, in.AAD)
	if err != nil {
		return meta.DecryptOutput{}, err
	}
	// Thread the KMS request id for CloudTrail correlation (forensic audit join).
	reqID, _ := awsmiddleware.GetRequestIDMetadata(out.ResultMetadata)
	return meta.DecryptOutput{Plaintext: plaintext, KMSRequestID: reqID}, nil
}

// openEnvelope parses [version|nonce|ct] and AES-256-GCM opens it with kek+aad.
func openEnvelope(kek, env, aad []byte) ([]byte, error) {
	if len(env) < 1+nonceLen {
		return nil, fmt.Errorf("piikms: envelope too short (%d bytes)", len(env))
	}
	if env[0] != envelopeVersion {
		return nil, fmt.Errorf("piikms: unsupported envelope version %d", env[0])
	}
	nonce := env[1 : 1+nonceLen]
	ct := env[1+nonceLen:]
	gcm, err := newGCM(kek)
	if err != nil {
		return nil, err
	}
	plaintext, err := gcm.Open(nil, nonce, ct, versionedAAD(env[0], aad))
	if err != nil {
		// Tag failure = tamper OR AAD mismatch OR wrong key. Do not leak which.
		return nil, fmt.Errorf("piikms: GCM open failed (tamper/AAD/key mismatch): %w", err)
	}
	return plaintext, nil
}

// versionedAAD prepends the envelope version byte to the caller AAD so the
// AEAD tag authenticates the version (anti-downgrade). Returns a fresh slice
// (never aliases/mutates the caller's aad).
func versionedAAD(version byte, aad []byte) []byte {
	out := make([]byte, 0, 1+len(aad))
	out = append(out, version)
	out = append(out, aad...)
	return out
}

func newGCM(key []byte) (cipher.AEAD, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("piikms: aes cipher: %w", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("piikms: gcm: %w", err)
	}
	return gcm, nil
}

func zeroize(b []byte) {
	for i := range b {
		b[i] = 0
	}
}

// mapKMSErr maps AWS KMS errors to the meta sentinels: permanent
// unreadable-key states → ErrPIIErased; transient → ErrKMSUnavailable.
func mapKMSErr(err error) error {
	if err == nil {
		return nil
	}
	var notFound *kmstypes.NotFoundException
	var invalidState *kmstypes.KMSInvalidStateException // key pending deletion / disabled state
	var disabled *kmstypes.DisabledException
	var invalidCT *kmstypes.InvalidCiphertextException
	if errors.As(err, &notFound) || errors.As(err, &invalidState) || errors.As(err, &disabled) || errors.As(err, &invalidCT) {
		return fmt.Errorf("%w: %v", meta.ErrPIIErased, err)
	}
	var unavailable *kmstypes.KeyUnavailableException
	var internal *kmstypes.KMSInternalException
	var throttling *kmstypes.LimitExceededException
	if errors.As(err, &unavailable) || errors.As(err, &internal) || errors.As(err, &throttling) {
		return fmt.Errorf("%w: %v", meta.ErrKMSUnavailable, err)
	}
	// Unknown → transient (fail-safe for reads: retry rather than declare erased).
	return fmt.Errorf("%w: %v", meta.ErrKMSUnavailable, err)
}
