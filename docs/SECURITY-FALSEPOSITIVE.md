# Antivirus False Positive — Go binaries flagged `Gen:Variant.Tedy.*`

**TL;DR:** Bitdefender (and occasionally other AV engines) flag our compiled Go
binaries — most reliably the `admin` CLI / its test binary — as
`Gen:Variant.Tedy.821107` (or similar `Gen:Variant.*` / `Gen:Heur.*`). **This is
a confirmed FALSE POSITIVE.** The binary is built from the source in this repo;
it contains no malware. Do not be alarmed, do not assume a compromise. This note
records the evidence and the remediation.

First observed: 2026-05-31, on `admin.test.exe` (the `services/admin-cli/cmd/admin`
Go test binary), during normal `go test`, after 076 Slice C linked the PII
crypto-shred (AWS-KMS + AES-GCM) code path into the `admin` binary.

---

## What the detection means

`Gen:Variant.Tedy.*` is a **generic machine-learning / heuristic** verdict, NOT a
signature match against known malware. It scores a file by structural
resemblance to malware families. It is a well-documented false-positive magnet
for **unsigned, statically-linked, pure-Go binaries** — the Go runtime's layout,
plus a large embedded crypto + RNG surface, resembles packed/ransomware tooling
to the heuristic.

## Why *our* binary trips it (root cause, evidence-based)

Three factors stack up; none is malicious:

1. **Unsigned, statically-linked, pure-Go binary.** No Authenticode signature,
   everything linked into one image, no cgo. This alone is the single biggest
   AV-FP factor for Go programs across vendors.

2. **A large statically-linked crypto + RNG surface.** Go 1.25 links its
   **FIPS-140 crypto module** into the binary. `go list -deps` shows, among
   others: `crypto/aes`, `crypto/cipher`, `crypto/internal/fips140/aes/gcm`,
   `.../sha256`, `.../sha512`, `.../sha3`, `.../hmac`, `.../drbg` (a determin-
   istic random-bit generator), `.../ecdh`, `.../edwards25519`. A big block of
   AES-GCM + hashing + **RNG** symbols is exactly what ransomware heuristics
   weight heavily.

3. **Our GDPR crypto-shred semantics resemble ransomware at the API level.**
   The 076 PII feature *encrypts data (AES-256-GCM) and then destroys the key*
   (`piikms.DestroyKEK` → AWS KMS `ScheduleKeyDeletion` + a `destroyed_at`
   marker). "Encrypt, then destroy the key" is structurally identical to what
   ransomware does — even though here it is the *legitimate* mechanism for GDPR
   Art. 17 right-to-be-forgotten. This is almost certainly why `cmd/admin`
   started tripping the heuristic only *after* Slice C linked this path in
   (other admin-cli test binaries, which don't link KMS/crypto-shred, do not
   trip it).

## Evidence it is NOT malware

Read-only audit of the first-party source (`services/admin-cli`, `sdks/go/piikms`,
`contracts/pii`):

- ❌ No `os/exec` / `exec.Command` (no process spawning) in our code.
- ❌ No direct `syscall.*`, no `unsafe.*`.
- ❌ No `net.Dial` / `http.Get|Post` beaconing in our code.
- ❌ No `//go:embed` payloads, no `plugin.*`, no UPX/packing, no obfuscation.
- ❌ No cgo (`import "C"`) — pure Go.
- ✅ What it *does* contain: AES-256-GCM via the Go standard library, AWS KMS
  API calls (`GenerateDataKey`, `Decrypt`, `ScheduleKeyDeletion`), `pgx`
  Postgres queries, JWT (RS256) verification, YAML/JSON parsing.

> Note: `go list -deps` *does* list `net`, `syscall`, `os/exec`, and `unsafe` in
> the ~322-package transitive closure. Those are pulled in by the **Go standard
> library and `aws-sdk-go-v2`** (the HTTP client for the KMS API, DNS
> resolution, and the credential-process provider) — they are **not invoked by
> our code**. Every Go binary that speaks to a cloud API links these.

The binary is fully **reproducible from source**: dependencies are pinned in the
per-module `go.mod` / `go.sum`. The dep set is entirely mainstream
(`aws-sdk-go-v2`, `jackc/pgx`, `golang-jwt/jwt`, `google/uuid`, `gopkg.in/yaml`).

## Impact on delivery — important

**The product is unaffected.** LoreWeave is **cloud-hosted on AWS in Linux
containers** (ECS/Docker); end users use the **web frontend** → gateway →
services and **never receive a Go binary**. `admin-cli` is an **internal
operator tool** that runs **server-side on Linux**, where Windows AV is not in
the loop. This false positive surfaces **only on a Windows developer/operator
workstation** running a desktop AV during `go build` / `go test`.

## How to verify for yourself

- **VirusTotal**: upload the binary. Expect only a small minority of engines
  (typically 1–3 of ~70) to raise a *generic/heuristic* verdict; signature-based
  engines pass. A handful of heuristic hits on an unsigned Go binary is the
  normal FP signature, not a real infection.
- **Inspect the surface**: `go -C services/admin-cli list -deps ./cmd/admin` —
  every package is standard.
- **Rebuild reproducibly** from the pinned `go.sum` and diff.

## Remediation

### Developers / operators on Windows (now)
Add a **folder exclusion** in your AV so freshly-built Go binaries aren't
scanned/quarantined:

> Bitdefender → **Protection → Antivirus → ⚙ Settings → Manage Exceptions →
> + Add an Exception** → add each path, enable for **Antivirus** (and On-Access /
> Advanced Threat Defense if shown) → Save.

Recommended exclusions:
- `D:\Works\gotmp` — `GOTMPDIR` is set here so all `go test` binaries land in one
  excludable folder. (Set via `setx GOTMPDIR "D:\Works\gotmp"`; new shells/reboot
  to take effect.)
- `%LocalAppData%\go-build` — the Go build cache.

One-off workaround without an exclusion (builds to a stable, already-cleared
path instead of the AV-watched temp dir):
```
go -C services/admin-cli test -c -o admin_cmd_test.exe ./cmd/admin
./services/admin-cli/admin_cmd_test.exe -test.count=1
```

### If we ever distribute a Windows binary (before shipping)
1. **Authenticode code-signing** with a trusted publisher certificate — signed
   binaries from a known publisher do not trip generic heuristics. This is the
   industry-standard fix and the prerequisite for any Windows distribution.
2. **Submit a false-positive report** to Bitdefender (and any other flagging
   vendor); Go FPs are usually whitelisted within days.
3. Prefer shipping/running as **Linux container images** (our actual deploy
   target) — no desktop AV involved.

Tracked as a deferral: **`D-WINDOWS-CODE-SIGN`** — code-sign + FP-report any
distributable Windows binary before release.

---

*If a NEW detection appears that is NOT a generic `Gen:Variant.*` / `Gen:Heur.*`
heuristic — e.g. a named, signature-based malware family — do not dismiss it:
re-audit the dependency diff (`go.sum` changes) and the source before trusting
the build.*
