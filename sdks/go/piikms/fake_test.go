package piikms

import (
	"context"
	"crypto/rand"
	"errors"

	awskms "github.com/aws/aws-sdk-go-v2/service/kms"
)

// fakeKMS is a FAITHFUL in-process KMS: it really wraps/unwraps the KEK with
// AES-256-GCM under a fixed fake master key (NOT XOR), so the
// ProvisionKEK→Encrypt→Decrypt round-trip exercises real crypto. Errors are
// injectable for error-mapping tests; ScheduleKeyDeletion calls are recorded.
type fakeKMS struct {
	master     []byte // 32B fixed fake master key
	decryptErr error  // injected into Decrypt
	genErr     error  // injected into GenerateDataKey
	scheduled  []string
}

func newFakeKMS() *fakeKMS {
	m := make([]byte, 32)
	for i := range m {
		m[i] = byte(i + 1)
	}
	return &fakeKMS{master: m}
}

func (f *fakeKMS) wrap(kek []byte) []byte {
	gcm, _ := newGCM(f.master)
	nonce := make([]byte, nonceLen)
	_, _ = rand.Read(nonce)
	return append(nonce, gcm.Seal(nil, nonce, kek, nil)...)
}

func (f *fakeKMS) unwrap(blob []byte) ([]byte, error) {
	if len(blob) < nonceLen {
		return nil, errors.New("fakeKMS: short blob")
	}
	gcm, _ := newGCM(f.master)
	return gcm.Open(nil, blob[:nonceLen], blob[nonceLen:], nil)
}

func (f *fakeKMS) GenerateDataKey(_ context.Context, in *awskms.GenerateDataKeyInput, _ ...func(*awskms.Options)) (*awskms.GenerateDataKeyOutput, error) {
	if f.genErr != nil {
		return nil, f.genErr
	}
	kek := make([]byte, kekLen)
	if _, err := rand.Read(kek); err != nil {
		return nil, err
	}
	return &awskms.GenerateDataKeyOutput{Plaintext: kek, CiphertextBlob: f.wrap(kek), KeyId: in.KeyId}, nil
}

func (f *fakeKMS) Decrypt(_ context.Context, in *awskms.DecryptInput, _ ...func(*awskms.Options)) (*awskms.DecryptOutput, error) {
	if f.decryptErr != nil {
		return nil, f.decryptErr
	}
	kek, err := f.unwrap(in.CiphertextBlob)
	if err != nil {
		return nil, err
	}
	return &awskms.DecryptOutput{Plaintext: kek, KeyId: in.KeyId}, nil
}

func (f *fakeKMS) ScheduleKeyDeletion(_ context.Context, in *awskms.ScheduleKeyDeletionInput, _ ...func(*awskms.Options)) (*awskms.ScheduleKeyDeletionOutput, error) {
	if in.KeyId != nil {
		f.scheduled = append(f.scheduled, *in.KeyId)
	}
	return &awskms.ScheduleKeyDeletionOutput{}, nil
}

var _ kmsAPI = (*fakeKMS)(nil)
