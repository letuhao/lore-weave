<!-- CHUNK-META
chunk: SR10_supply_chain.md
origin: direct-authored 2026-04-24
origin_branch: mmo-rpg/design-resume
note: Not produced by scripts/chunk_doc.py split; authored as new SR-series content extending SR1-SR9.
-->

## 12AM. Supply Chain Security — SR10 Resolution (2026-04-24)

**Origin:** SRE Review SR10 — prior work secured the **runtime** (S9 prompt assembly · S11 service auth · S12 WebSocket · SR6 dependency failure) but left the **build path** untouched. A compromised upstream library, an unsigned container image, or a floating dependency version is just as dangerous as a runtime bug — and harder to detect because it enters through the supply chain. SR10 extends I12 (no hardcoded secrets) from runtime discipline into build-time supply chain: SBOM + dep pinning + image signing + CVE gating + 3rd-party vetting + build provenance.

### 12AM.1 Problems closed

1. Floating dependency versions (no hash pinning)
2. Unsigned container images in prod
3. No SBOM for post-incident dep audit
4. CVE disclosures discovered late (reactive, not gated)
5. 3rd-party libraries added ad-hoc with no vetting
6. Build provenance unverifiable (no SLSA level)
7. Secret scanning limited to linting (I12); misses git history + binary artifacts
8. Vendor compromise response undefined
9. Reproducible builds not enforced
10. No supply chain incident playbook
11. Transitive dep vulnerabilities invisible

### 12AM.2 Layer 1 — SBOM Generation + Retention

Every service generates an SBOM at build; format: **CycloneDX 1.5** (structured + attestation-ready). SPDX interop supported for external sharing (compliance / vendor asks).

**Generation:** `syft` (or equivalent) scans the built artifact; output committed alongside the built container image in registry with matching tag. Per-build SBOM stored at:
- **Artifact registry** (primary): `sboms/<service>/<version>.cdx.json`
- **`supply_chain_events` audit row** (index; 3y retention — see §12AM.10)
- **5-year cold archive** for compliance (MinIO bucket `lw-sbom-archive` per S8-D3 retention tier)

**Contents:** every dependency (direct + transitive) with `name` · `version` · `license` · `hash` · `source URL` · `declared_in` (go.sum / package-lock / Pipfile.lock).

**Queries supported** (via `admin-cli supply-chain query`):
- "which services use log4j < 2.17?"
- "show all GPL-licensed deps in platform-paid services"
- "what changed in auth-service deps between v1.2.3 and v1.2.4?"

Per-SBOM storage ~1-5MB; at V3 scale (~20 services × 100 builds/year × 5y) < 50 GB total. Manageable.

### 12AM.3 Layer 2 — Dependency Pinning Discipline (proposed invariant I18)

**Rule:** every dependency declaration committed to the repo MUST include a hash. No floating versions. No SemVer ranges without hash pin.

**Per-language enforcement:**

| Language | Manifest | Hash mechanism | CI lint |
|---|---|---|---|
| Go | `go.mod` + `go.sum` | SHA-256 per module version (native `go mod`) | `go mod verify` passes; CI fails if `go.sum` missing entries |
| Python | `requirements.txt` (preferred: `uv.lock` or `poetry.lock`) | `--require-hashes` mode; per-dep `--hash=sha256:...` | `pip install --require-hashes` passes |
| TypeScript | `package-lock.json` (not yarn.lock alone) | `integrity` field per package (SHA-512) | `npm ci` passes (strict lockfile check) |
| Docker base images | `FROM image@sha256:...` not `FROM image:tag` | Digest pinning | `dockerfile-digest-lint.sh` |

**Proposed invariant I18:** "Every dependency declaration committed to the repo includes a cryptographic hash. No floating versions. No SemVer ranges without hash pin. All Docker base images referenced by digest."

**Status of I18:** **PENDING architect sign-off via POST-REVIEW** — not self-authorized per SR6 process lesson. If approved → joins I17 in `00_foundation/02_invariants.md` with enforcement point `scripts/dep-pinning-lint.sh`. If rejected → SR10-D2 stays decision-class without invariant status.

**Update workflow (not "never update"):**
- Dep updates follow SR5-D1 `minor` deploy class (reviewable diff + migration plan)
- Automated Dependabot / Renovate PRs allowed, but must regenerate lockfile + update SBOM in same PR
- Transitive dep changes surface in diff; reviewer approves both direct + transitive deltas

### 12AM.4 Layer 3 — Container Image Signing

All container images deployed to staging or prod MUST be signed by the platform build key using **cosign + sigstore**.

**Signing flow:**
1. CI builds image + generates CycloneDX SBOM (L1)
2. `cosign sign --key=$BUILD_SIGNING_KEY <image>` — signature pushed to registry alongside image
3. `cosign attest --predicate=<sbom>.cdx.json --type=cyclonedx` — SBOM attached as attestation
4. `cosign attest --predicate=<slsa-provenance>.json --type=slsaprovenance` — provenance (L6)

**Admission policy (Kubernetes):**
- Cluster policy (`cosign-admission-policy.yaml`) rejects unsigned images
- Policy identifies expected signer key by image registry prefix (`lw-*` → platform key; external images → per-allowlisted vendor key)
- No bypass except `admin/supply-chain-freeze` emergency (L10)

**Signing key management:**
- `BUILD_SIGNING_KEY` stored in AWS KMS (S11-D6 Vault pattern)
- Access restricted to CI SVID + security on-call (break-glass rotation per S11-D10)
- Key rotation: quarterly (matches SR2-D8 cadence); old signatures remain valid (detached signatures)

### 12AM.5 Layer 4 — CVE Scanning + Severity Gating

Scanner: `trivy` (or equivalent) runs on every build + nightly scheduled scan of all in-prod images.

**Severity gating (CI):**

| Severity | Build action | Deploy action |
|---|---|---|
| **Critical** (CVSS 9.0-10.0) | Block merge | Block deploy; `admin/cve-override` required for bounded bypass |
| **High** (CVSS 7.0-8.9) | Block merge unless reviewer approves with `known-cve-high` label + tracking ticket + 30-day fix deadline | Block deploy if no tracking ticket |
| **Medium** (CVSS 4.0-6.9) | Ticket created; doesn't block merge | Doesn't block deploy |
| **Low** (CVSS 0.1-3.9) | Log only | No action |

**Nightly scan** (`scripts/cve-nightly.sh`):
- Scans all in-prod image tags
- Newly-disclosed CVE in an in-prod image → `lw_supply_chain_cve_detected` fires SR9 alert + creates tracking ticket + notifies security on-call
- Critical CVE in in-prod image → SEV1 auto-declared per SR2-D9 security fast-path

**`admin/cve-override`** (S5 Tier 2 Griefing):
- Bounded 72h (longer than capacity-override; CVE patching takes time)
- Requires incident ticket reference + remediation ETA + SRE approval
- Post-expire report + auto-escalation if unremediated at ETA

### 12AM.6 Layer 5 — 3rd-Party Library Vetting

New direct dependency requires architect-level review before adoption (same workflow as new invariant / new service / new dep class per SR6-D1).

**Vetting checklist** at `docs/sre/supply-chain/dep-vetting-template.md`:
- [ ] **License compatibility** — MIT / BSD / Apache-2.0 default-approved; LGPL / MPL review; GPL / AGPL require legal + architect approval
- [ ] **Maintenance signal** — release cadence, issue response time, maintainer diversity
- [ ] **Security track record** — CVE history, response time to disclosures
- [ ] **Dependency depth** — transitive dep count + licenses + risk
- [ ] **Scope justification** — why this lib vs alternatives or in-house
- [ ] **Alternative evaluated** — documented comparison (at minimum: one alternative considered + rejected with reason)
- [ ] **Upgrade path** — major-version upgrade process documented

**Allowlist registry:** `contracts/supply_chain/dep_allowlist.yaml`:

```yaml
- name: github.com/example/lib
  version_constraint: "^1.0"       # SemVer constraint; specific versions pinned separately in go.sum
  language: go
  approved_by: <architect-actor-ref>
  approved_at: 2026-04-24
  justification: "Canonical library for X; vetted against Y alternative; license MIT."
  license: MIT
  cve_track_record: "Clean through 2026; responsive maintainer"
  review_cadence: annual            # Re-review at cadence; allowlist entries expire otherwise
```

**CI enforcement** (`scripts/dep-allowlist-lint.sh`):
- Import graph scanned vs allowlist on every PR
- New direct dep not in allowlist = lint fail
- `admin/dep-vet-approve` (S5 Tier 2) adds row + commit; PR cannot merge without reviewer + architect co-sign

**Annual review:** each allowlist entry's `approved_at` + `review_cadence` checked; overdue entries flagged for re-vetting at quarterly cadence (SR2-D8).

### 12AM.7 Layer 6 — Build Provenance (SLSA)

**V1 target: SLSA Level 2.** Level 3 V2+ with hermetic isolated builders.

**Level 2 requirements** (all met via CI config):
- Scripted, versioned build (Git-pinned CI config)
- Hosted build platform (GitHub Actions / CircleCI)
- Provenance generated + signed
- Provenance validates image tag matches source commit

**Provenance generation:** `slsa-github-generator` (or equivalent) emits `slsaprovenance` attestation per build, attached via cosign (L4).

**Provenance contents:**
- `buildType` — deterministic CI workflow identifier
- `builder.id` — GitHub Actions runner + version
- `invocation.configSource` — Git repo + commit SHA + path
- `materials` — all input artifacts with hashes
- `metadata.completeness` — declares which fields were independently verifiable

**V2+ Level 3 upgrades:**
- Hermetic builds (no network during build; all deps fetched pre-build)
- Isolated ephemeral builders (no shared state between builds)
- Two-person integrity review for privileged build steps

### 12AM.8 Layer 7 — Secret Scanning (extends I12)

**I12 says:** no hardcoded secrets or model names in source code. SR10-L7 extends enforcement to **3 scan points**:

1. **Pre-commit hook** (`scripts/pre-commit-secret-scan.sh`): runs `gitleaks` locally before commit; catches most obvious leaks; dev can bypass with `--no-verify` but CI re-runs
2. **CI scan** (`scripts/ci-secret-scan.sh`): runs on every PR + main-branch push; catches what pre-commit missed; failing scan blocks merge
3. **Git-history scan** (`scripts/history-secret-scan.sh`): monthly cron scans entire repo history; detects secrets committed + rolled-back without rotation; auto-creates incident if detected

**Scope of secrets:**
- API keys (AWS / LLM providers / third-party services)
- Database passwords
- Signing keys + private keys
- OAuth client secrets
- JWT signing secrets
- Any `.env` file contents committed
- Any value tagged `@secret` in code comments

**Baseline:** `contracts/supply_chain/secret-scan-baseline.yaml` lists known false-positives with justification (e.g., placeholder strings in tests); new additions require security approval.

**Detection response:**
- Critical (actual secret, not placeholder) → SEV1 incident per SR2-D9 security fast-path; rotation required
- `admin/supply-chain-freeze` auto-considered if git-history scan shows multiple commits affected

### 12AM.9 Layer 8 — Supply Chain Incident Response

Dedicated runbook at `docs/sre/runbooks/supply-chain/` (new subfolder in SR3 library):

| Scenario | Runbook | Severity |
|---|---|---|
| CVE disclosed in in-prod dep | `cve-in-prod.md` | SEV1 (auto per L5 nightly scan) |
| Vendor package account compromised (e.g., npm account takeover) | `vendor-compromise.md` | SEV0 |
| Signing key compromise | `signing-key-compromise.md` | SEV0; triggers `admin/supply-chain-freeze` |
| Build system compromise | `build-system-compromise.md` | SEV0; triggers `admin/supply-chain-freeze` + credential rotation |
| Secret leak detected in history | `secret-leak-history.md` | SEV1; triggers rotation workflow |
| Transitive dep vulnerability | `transitive-cve.md` | SEV2 by default; escalates based on exploitability |

**SR3 V1 runbook gate extension:** adds 6 runbooks for SR10 scenarios. V1 runbook total reconciled: **27 base (SR3) + 5 chaos (SR7) + 1 drain-shard (SR8) + 6 supply-chain (SR10) = 39 runbooks at V1 launch**.

**`admin/supply-chain-freeze`** (S5 Tier 1 Destructive) — platform-wide deploy halt during supply chain incident:
- Dual-actor + 100+ char reason + incident ticket reference + 24h cooldown before re-enable
- Integrates with SR5-D2 deploy freeze mechanism (security-triggered pattern)
- Exceptions: emergency patches only with `break-glass-deploy` label (same as SR5)

### 12AM.10 Layer 9 — Build Reproducibility + `supply_chain_events` Audit

**Reproducibility target (V1):** builds of the same commit SHA + same builder config produce byte-identical artifacts modulo timestamp fields (deterministic). Non-deterministic builds are a bug; tracked at `docs/sre/supply-chain/non-reproducible-builds.md`.

**Reproducibility CI check** (V1+30d): random 10% of CI builds re-run on a clean builder; diff artifacts; report mismatches. Mismatch → investigation but doesn't block merge (V1); V2+ blocks.

**`supply_chain_events` audit table:**

```sql
CREATE TABLE supply_chain_events (
  event_id              UUID PRIMARY KEY,
  event_type            TEXT NOT NULL,                   -- 'sbom_generated' | 'image_signed'
                                                         -- | 'cve_detected' | 'cve_override_granted'
                                                         -- | 'dep_added_to_allowlist' | 'dep_removed_from_allowlist'
                                                         -- | 'secret_detected' | 'signing_key_rotated'
                                                         -- | 'supply_chain_freeze_activated' | 'supply_chain_freeze_cleared'
                                                         -- | 'provenance_verification_failed'
  service               TEXT,                            -- service affected (nullable for platform-wide events)
  artifact_ref          TEXT,                            -- image tag / SBOM hash / CVE ID / dep name
  severity              TEXT,                            -- 'critical' | 'high' | 'medium' | 'low' | 'info'
  details               JSONB,                           -- event-type-specific fields (CVE CVSS, SBOM metadata, etc.)
  occurred_at           TIMESTAMPTZ NOT NULL,
  resolved_at           TIMESTAMPTZ,
  related_incident_id   UUID,                            -- SR2-D7 link if promoted to incident
  actor                 UUID                             -- user_ref_id for manual actions; NULL for automated
);

CREATE INDEX ON supply_chain_events (event_type, occurred_at DESC);
CREATE INDEX ON supply_chain_events (service, occurred_at DESC) WHERE service IS NOT NULL;
CREATE INDEX ON supply_chain_events (severity, occurred_at DESC) WHERE severity IN ('critical', 'high');
CREATE INDEX ON supply_chain_events (event_type, resolved_at) WHERE resolved_at IS NULL;
```

**Retention:** **3 years** (matches `chaos_drills` per SR7-D8; compliance-relevant but not perpetual).
**PII classification:** `none` (artifact refs + severity only).
**Write path:** via `MetaWrite()` (I8); append-only with narrow-column allowlist for `resolved_at` + `related_incident_id` updates.

### 12AM.11 Layer 10 — V1 Minimal Bar

**V1 launch gate:**

1. **SBOM generation** — all 19 services (12 existing + 7 MMO-RPG V1) generate CycloneDX SBOM on every build; committed alongside image to registry
2. **Dep pinning** — all manifests pass `dep-pinning-lint.sh`; I18 (if approved) enforced
3. **Image signing** — all staging + prod images signed via cosign; Kubernetes admission policy active
4. **CVE gating** — CI fails merge on critical/high CVEs; nightly scan + alert active
5. **Allowlist** — all current direct deps populated in `contracts/supply_chain/dep_allowlist.yaml`; `dep-allowlist-lint.sh` passing
6. **SLSA Level 2** — provenance attestation generated + attached to every image
7. **Secret scanning** — pre-commit + CI + baseline git-history scan clean
8. **6 supply-chain runbooks** committed (L8); integrated into SR3 V1 gate (27→39)
9. **`supply_chain_events` table + MetaWrite integration** operational
10. **`admin/supply-chain-freeze`** + override commands registered in admin-cli per S5 classification

**V1+30d evolution:**
- L9 reproducibility CI check active (10% sample re-runs)
- L7 history scan monthly cadence operational
- L6 SLSA Level 2 provenance verification at admission (not just attestation-generation)

**V2+ evolution:**
- SLSA Level 3 (hermetic builds, isolated builders)
- L9 reproducibility CI check blocks merge (not just reports)
- Automated vendor-compromise detection (e.g., monitor npm / PyPI registries)
- Signed SBOM distribution to external consumers (vendor compliance asks)

### 12AM.12 Interactions + V1 split + what this resolves

**Interactions:**

| With | Interaction |
|---|---|
| I12 (no hardcoded secrets) | SR10-L7 operationalizes I12 enforcement via 3-scan-point discipline |
| I14 (additive-first schema) | `supply_chain_events` table follows additive-first; new event_types added to enum without breaking change |
| SR1-D6 | `lw_supply_chain_cve_detected` derivation-rule registered via SR9-D2 |
| SR2-D7 | `supply_chain_events.related_incident_id` populates SR2 incidents table |
| SR2-D9 | Security fast-path auto-declares SEV1 for critical CVE in-prod; SEV0 for signing-key compromise |
| SR3-D3 | V1 runbook gate extended to **39** (27 base + 5 chaos + 1 drain-shard + 6 supply-chain) |
| SR3-D5 | Alert-runbook CI lint trio extended to cover supply_chain_events-derived alerts |
| SR5-D2 | `admin/supply-chain-freeze` is the security-triggered freeze mechanism; extends SR5-D2 |
| SR5-D1 | Dep updates = minor deploy class; signed-image re-tag = patch class |
| SR6-D1 | `contracts/dependencies/matrix.yaml` covers runtime deps; `contracts/supply_chain/dep_allowlist.yaml` covers build-time libs — distinct but cross-referenced |
| SR9-D2 | CVE alerts registered in `contracts/alerts/rules.yaml`; severity gating determines action-class |
| S11-D6 | Signing key stored in Vault per SVID-bound policy; key rotation shares S11 mechanism |
| S11-D10 | Break-glass access required for signing-key rotation during incident |
| ADMIN_ACTION_POLICY §R4 | 3 new commands: `admin/cve-override` Tier 2 · `admin/dep-vet-approve` Tier 2 · `admin/supply-chain-freeze` Tier 1 |

**Accepted trade-offs:**

| Cost | Justification |
|---|---|
| SBOM generation adds CI time | ~30s-2min per build; enables post-incident forensics; compliance-ready |
| Image signing adds deploy latency | ~5-10s per image; cryptographic integrity worth it |
| CVE gating blocks merges | Forces prompt patching; trackin ticket + ETA provides escape hatch |
| Dep allowlist adds vetting friction | New direct deps are rare; friction pushes in-house implementation or reuse existing allowlisted libs |
| SLSA Level 2 is mid-tier | Level 3 hermetic builds is V2+ cost-benefit; Level 2 catches most supply chain attacks |
| 3-scan-point secret scanning overlaps | Belt-and-suspenders; any one scanner missing a pattern is caught by another; false-positive baseline manages noise |
| `admin/supply-chain-freeze` halts all deploys | Existential risk during active supply chain attack; emergency patch exception via break-glass |

**What this resolves:**

- ✅ Floating dep versions — L2 pinning + CI lint + (if approved) I18
- ✅ Unsigned images — L3 cosign + admission policy
- ✅ Missing SBOM — L1 generation + retention + queryable
- ✅ Reactive CVE handling — L4 gating + nightly scan + alert
- ✅ Ad-hoc 3rd-party deps — L5 vetting checklist + allowlist
- ✅ Unverifiable build provenance — L6 SLSA Level 2
- ✅ Incomplete secret scanning — L7 3-scan-point discipline
- ✅ Undefined vendor-compromise response — L8 6 dedicated runbooks
- ✅ Non-reproducible builds — L9 target + V1+30d check
- ✅ No supply-chain audit trail — L9 `supply_chain_events`
- ✅ Transitive vulnerabilities hidden — L1 SBOM + L4 nightly scan + L2 hash pinning

**V1 / V1+30d / V2+ split:**

- **V1:**
  - L1 SBOM generation + retention
  - L2 dep pinning + CI lint (+ I18 if approved)
  - L3 image signing + admission policy
  - L4 CVE gating (critical/high block; nightly scan + alerts)
  - L5 allowlist registry + vetting checklist
  - L6 SLSA Level 2 provenance
  - L7 3-scan-point secret scanning
  - L8 6 runbooks + `admin/supply-chain-freeze`
  - L9 `supply_chain_events` audit
  - L10 V1 gate checklist
- **V1+30d:**
  - L9 reproducibility CI check (10% sample)
  - L7 history scan monthly cadence
  - L6 provenance verification at admission (not just generation)
- **V2+:**
  - SLSA Level 3 (hermetic builds)
  - L9 reproducibility blocks merge
  - Vendor-compromise detection automation
  - Signed SBOM external distribution

**Residuals (deferred):**
- Policy-as-code framework (OPA / Rego) for admission policy — V2+ evaluation
- Private package registry mirror — V2+ if external registry availability becomes a concern
- Cross-vendor SBOM exchange protocol — V3+ industry-standard when mature

**Decisions locked (10 + 1 pending):**
- **SR10-D1** SBOM generation per service at build time; CycloneDX 1.5 format; stored in artifact registry + `supply_chain_events` index + 5y cold archive
- **SR10-D2** Per-language dep pinning with hash (Go `go.sum` · Python `--require-hashes` · TS `package-lock.json integrity` · Docker digest pins); `dep-pinning-lint.sh` CI enforcement
- **SR10-D3** Container image signing via cosign + sigstore; Kubernetes admission policy rejects unsigned; signing key in Vault per S11-D6; quarterly rotation
- **SR10-D4** CVE severity gating (Critical blocks merge + deploy · High blocks merge w/o tracking ticket + 30d fix · Medium tickets · Low logs); trivy scanner; nightly in-prod scan; auto-alert integration via SR9-D2
- **SR10-D5** 3rd-party library vetting checklist + allowlist registry at `contracts/supply_chain/dep_allowlist.yaml`; `admin/dep-vet-approve` S5 Tier 2; annual review cadence; license tier (MIT/BSD/Apache default-approved, LGPL/MPL review, GPL/AGPL legal+architect)
- **SR10-D6** SLSA Level 2 V1 target with slsa-github-generator provenance attached via cosign; Level 3 V2+ with hermetic builders
- **SR10-D7** Secret scanning extends I12 via 3-scan-point discipline (pre-commit + CI + monthly history scan); gitleaks baseline with false-positive justification; critical detection = SEV1 auto-declared
- **SR10-D8** Supply chain incident runbook library — 6 runbooks (cve-in-prod · vendor-compromise · signing-key-compromise · build-system-compromise · secret-leak-history · transitive-cve); integrated into SR3-D3 V1 gate; total reconciled to **39 runbooks**
- **SR10-D9** Build reproducibility V1 target + `supply_chain_events` audit table (3y retention; MetaWrite append-only; 11-enum event_type); V1+30d 10% CI re-run sample; V2+ blocks merge on mismatch
- **SR10-D10** V1 minimal bar — 10-item launch gate (SBOM / pinning / signing / CVE gating / allowlist / SLSA L2 / secret scanning / 6 runbooks / `supply_chain_events` / admin commands)
- **SR10-D11** **PENDING architect approval** — proposed invariant I18 "every dep pinned with hash; floating versions forbidden; Docker base images digest-pinned". If approved → joins I17 in `00_foundation/02_invariants.md` with enforcement `dep-pinning-lint.sh`. If rejected → SR10-D2 stays decision-class.

**Features added (11):**
- **IF-43** Supply chain registry (`contracts/supply_chain/`: dep_allowlist.yaml + secret-scan-baseline.yaml + cve-policy.yaml)
- **IF-43a** SBOM generator (syft or equivalent; CycloneDX output)
- **IF-43b** Dep pinning enforcer (`dep-pinning-lint.sh`)
- **IF-43c** Container image signing + verification (cosign + Kubernetes admission policy)
- **IF-43d** CVE scanner + severity gate (trivy; critical/high blocks)
- **IF-43e** 3rd-party vetting workflow (checklist + allowlist CI lint + `admin/dep-vet-approve`)
- **IF-43f** SLSA Level 2 provenance attestation (slsa-github-generator + cosign attest)
- **IF-43g** 3-scan-point secret scanning (gitleaks pre-commit + CI + monthly history cron)
- **IF-43h** Supply chain runbook library (6 runbooks; integrates SR3 27-runbook gate → 39)
- **IF-43i** Build reproducibility check (V1+30d: 10% re-run sample; V2+: blocks merge)
- **IF-43j** `supply_chain_events` audit table + `admin/cve-override` + `admin/supply-chain-freeze` CLI

**Remaining SRE concerns (SR11-SR12) queued:** turn-based game reliability UX · observability cost + cardinality.
