package supply_chain

import (
	"context"
	"errors"
	"path/filepath"
	"runtime"
	"testing"
)

// TestLoadAndValidate_RealPolicyYAML pins that the cycle-19 shipped
// policy.yaml parses + validates.
func TestLoadAndValidate_RealPolicyYAML(t *testing.T) {
	_, thisFile, _, _ := runtime.Caller(0)
	path := filepath.Join(filepath.Dir(thisFile), "policy.yaml")
	p, err := LoadAndValidate(path, ModeStrict)
	if err != nil {
		t.Fatalf("LoadAndValidate(%s, strict): %v", path, err)
	}
	if p.Version != 1 {
		t.Errorf("Version = %d, want 1", p.Version)
	}
	if len(p.DepPinning.Ecosystems) < 5 {
		t.Errorf("expected at least 5 ecosystems; got %d", len(p.DepPinning.Ecosystems))
	}
	if p.SBOM.Format != "cyclonedx" {
		t.Errorf("SBOM.Format = %q, want cyclonedx", p.SBOM.Format)
	}
	if !p.LicenseAllowed("MIT") {
		t.Errorf("MIT not in allowlist")
	}
	if p.LicenseAllowed("GPL-3.0-only") {
		t.Errorf("GPL-3.0-only unexpectedly in allowlist")
	}
}

func TestParseAndValidate_RejectsUnsupportedVersion(t *testing.T) {
	bad := []byte(`version: 99
dep_pinning: {ecosystems: []}
sbom: {format: cyclonedx, spec_version: "1.5", emit_per_build: true, destination: {type: s3}, retention_days: 30}
license_allowlist: [MIT]
banned_packages: []
provenance: {enabled: false, signer: cosign}
`)
	_, err := ParseAndValidate(bad, ModeStrict)
	if !errors.Is(err, ErrUnsupportedVersion) {
		t.Errorf("err = %v, want ErrUnsupportedVersion", err)
	}
}

func TestPolicy_Validate_RejectsBadFields(t *testing.T) {
	mk := func() Policy {
		return Policy{
			Version: 1,
			DepPinning: DepPinning{Ecosystems: []EcosystemPolicy{{
				Ecosystem: EcosystemGo, Lockfile: "go.sum", Required: true,
			}}},
			SBOM:             SBOM{Format: "cyclonedx", SpecVersion: "1.5", EmitPerBuild: true, RetentionDays: 30},
			LicenseAllowlist: []string{"MIT"},
			Provenance:       Provenance{Enabled: false, Signer: "cosign"},
		}
	}
	cases := []struct {
		name   string
		mutate func(*Policy)
	}{
		{"unknown ecosystem", func(p *Policy) { p.DepPinning.Ecosystems[0].Ecosystem = "haskell" }},
		{"both lockfile and options", func(p *Policy) {
			p.DepPinning.Ecosystems[0].LockfileOptions = []string{"alt"}
		}},
		{"go without lockfile or options", func(p *Policy) {
			p.DepPinning.Ecosystems[0].Lockfile = ""
		}},
		{"bad sbom format", func(p *Policy) { p.SBOM.Format = "blob" }},
		{"empty sbom spec_version", func(p *Policy) { p.SBOM.SpecVersion = "" }},
		{"sbom retention 0", func(p *Policy) { p.SBOM.RetentionDays = 0 }},
		{"empty ecosystems", func(p *Policy) { p.DepPinning.Ecosystems = nil }},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			p := mk()
			c.mutate(&p)
			if err := p.Validate(); !errors.Is(err, ErrInvalidPolicy) {
				t.Errorf("err = %v, want ErrInvalidPolicy", err)
			}
		})
	}
}

func TestPolicy_Validate_RejectsBadProvenanceSigner(t *testing.T) {
	p := Policy{
		Version: 1,
		DepPinning: DepPinning{Ecosystems: []EcosystemPolicy{{Ecosystem: EcosystemGo, Lockfile: "go.sum", Required: true}}},
		SBOM:       SBOM{Format: "cyclonedx", SpecVersion: "1.5", EmitPerBuild: true, RetentionDays: 30},
		Provenance: Provenance{Enabled: true, Signer: "yoloware"},
	}
	if err := p.Validate(); !errors.Is(err, ErrProvenanceUnsupported) {
		t.Errorf("err = %v, want ErrProvenanceUnsupported", err)
	}
}

func TestPolicy_CheckPackage_Banned(t *testing.T) {
	p := Policy{
		BannedPackages: []BannedPackage{
			{Ecosystem: EcosystemRust, Name: "evil-crate", VersionGlob: "*", Reason: "test"},
		},
	}
	if err := p.CheckPackage(EcosystemRust, "evil-crate", "0.1.0"); !errors.Is(err, ErrPackageBanned) {
		t.Errorf("err = %v, want ErrPackageBanned", err)
	}
	if err := p.CheckPackage(EcosystemGo, "evil-crate", "0.1.0"); err != nil {
		t.Errorf("cross-ecosystem err = %v, want nil", err)
	}
	if err := p.CheckPackage(EcosystemRust, "ok-crate", "0.1.0"); err != nil {
		t.Errorf("clean err = %v, want nil", err)
	}
}

func TestSBOMBuffer_RingEvictsOldest(t *testing.T) {
	b := NewSBOMBuffer(2)
	b.Write(SBOMEmitRow{BuildID: "b1"})
	b.Write(SBOMEmitRow{BuildID: "b2"})
	b.Write(SBOMEmitRow{BuildID: "b3"}) // evicts b1
	rows := b.Drain()
	if len(rows) != 2 || rows[0].BuildID != "b2" || rows[1].BuildID != "b3" {
		t.Errorf("rows = %+v", rows)
	}
	if b.DroppedCount() != 1 {
		t.Errorf("dropped = %d, want 1", b.DroppedCount())
	}
}

func TestNoopVerifier_AlwaysUnverified(t *testing.T) {
	v := NoopVerifier{}
	r, err := v.Verify(context.Background(), "s3://x/y", "")
	if !errors.Is(err, ErrSignatureUnverified) {
		t.Errorf("err = %v, want ErrSignatureUnverified", err)
	}
	if r.Verified {
		t.Errorf("Verified = true, want false")
	}
}

func TestPolicyAwareVerifier_ShortCircuitsWhenDisabled(t *testing.T) {
	v := PolicyAwareVerifier{Policy: Policy{Provenance: Provenance{Enabled: false, Signer: "cosign"}}}
	r, err := v.Verify(context.Background(), "s3://x/y", "")
	if err != nil {
		t.Errorf("err = %v, want nil (provenance disabled)", err)
	}
	if !r.Verified {
		t.Errorf("Verified = false, want true (provenance disabled)")
	}
}

func TestPolicyAwareVerifier_FailsClosedWhenEnabledButNoDelegate(t *testing.T) {
	v := PolicyAwareVerifier{Policy: Policy{Provenance: Provenance{Enabled: true, Signer: "cosign"}}}
	_, err := v.Verify(context.Background(), "s3://x/y", "")
	if !errors.Is(err, ErrSignatureUnverified) {
		t.Errorf("err = %v, want ErrSignatureUnverified (fail-closed)", err)
	}
}

type acceptAllVerifier struct{}

func (acceptAllVerifier) Verify(_ context.Context, artifactRef, _ string) (VerifyResult, error) {
	return VerifyResult{Verified: true, Signer: "cosign", SignerIdentity: "ci@loreweave.dev", Notes: "ok"}, nil
}

func TestPolicyAwareVerifier_DelegatesWhenEnabled(t *testing.T) {
	v := PolicyAwareVerifier{
		Policy:   Policy{Provenance: Provenance{Enabled: true, Signer: "cosign"}},
		Delegate: acceptAllVerifier{},
	}
	r, err := v.Verify(context.Background(), "s3://x/y", "sig")
	if err != nil {
		t.Errorf("err = %v, want nil", err)
	}
	if !r.Verified || r.SignerIdentity == "" {
		t.Errorf("result = %+v, want verified+signed", r)
	}
}
