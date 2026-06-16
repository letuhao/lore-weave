// Package piikms is the production AWS-KMS adapter for the LoreWeave PII
// envelope (076 Slice B). It implements the cycle-3 contracts/meta.KMSClient
// (Decrypt) plus the encrypt/provision helpers, and a Postgres-backed
// contracts/pii.KEKManager (DestroyKEK), backed by real AWS KMS (LocalStack in
// dev).
//
// # Three-tier envelope (S08 §12X.2, authoritative)
//
//	per-user KMS CMK  ──wraps──▶  per-user KEK (pii_kek.key_material)  ──AES-256-GCM──▶  payload (pii_registry.encrypted_blob)
//
// Decrypt: KMS-decrypt key_material → plaintext KEK → AES-256-GCM open the
// payload envelope with the KEK. Encrypt/ProvisionKEK: KMS GenerateDataKey
// mints the KEK (returns plaintext + wrapped), then AES-256-GCM seals the
// payload with the plaintext KEK.
//
// Payload envelope layout: [1B version=1][12B nonce][AES-256-GCM ciphertext‖tag].
// The wrapped KEK is NOT in the envelope — it lives in pii_kek.key_material.
// AAD = meta.PIIAAD(user_ref_id, kek_id) (the single shared builder).
//
// # PER-USER CMK PRECONDITION (load-bearing)
//
// Crypto-shred (DestroyKEK) calls KMS ScheduleKeyDeletion on the KEK's
// kms_key_ref. This is co-tenant-SAFE ONLY because each pii_kek.kms_key_ref is
// a PER-USER CMK. Provisioning MUST allocate a distinct CMK per user. As a
// defense against mis-provisioning, DestroyKEK SUPPRESSES ScheduleKeyDeletion
// (marking destroyed_at only + logging) if any OTHER live KEK row still
// references the same kms_key_ref — turning a silent mass-erase into observable
// safe degradation. The authoritative erasure is always the per-row
// destroyed_at marker (OpenPII refuses to decrypt once it is set); KMS key
// deletion is defense-in-depth.
//
// Rotation note (Slice C): the GCM AAD binds kek_id, so a rotated KEK (new
// kek_id) cannot open blobs sealed under the old KEK — rotation MUST be a full
// decrypt-then-reseal, never a cheap re-wrap.
package piikms
