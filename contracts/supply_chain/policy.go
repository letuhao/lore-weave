package supply_chain

import (
	"bytes"
	"errors"
	"fmt"
	"os"
	"strings"

	"gopkg.in/yaml.v3"
)

// LoadMode mirrors observability/capacity.
type LoadMode int

const (
	ModeStrict LoadMode = iota
	ModeLax
)

// Ecosystem identifies a package ecosystem (matches dep-pinning-lint.sh).
type Ecosystem string

const (
	EcosystemGo     Ecosystem = "go"
	EcosystemRust   Ecosystem = "rust"
	EcosystemPython Ecosystem = "python"
	EcosystemJS     Ecosystem = "js"
	EcosystemDocker Ecosystem = "docker"
)

// EcosystemPolicy is one ecosystem entry under dep_pinning.ecosystems.
//
// Lockfile is the single canonical lockfile name (when there is one).
// LockfileOptions is the alternate-set (Python: uv.lock | poetry.lock;
// JS: package-lock.json | pnpm-lock.yaml). Exactly one of the two
// fields must be populated per entry.
type EcosystemPolicy struct {
	Ecosystem       Ecosystem `yaml:"ecosystem"`
	Lockfile        string    `yaml:"lockfile,omitempty"`
	LockfileOptions []string  `yaml:"lockfile_options,omitempty"`
	Required        bool      `yaml:"required"`
	Notes           string    `yaml:"notes,omitempty"`
}

// DepPinning is the top-level dep_pinning block.
type DepPinning struct {
	Ecosystems []EcosystemPolicy `yaml:"ecosystems"`
}

// SBOMDestination is the storage destination for emitted SBOMs.
type SBOMDestination struct {
	Type   string `yaml:"type"`   // s3 | local | minio
	Bucket string `yaml:"bucket,omitempty"`
	Prefix string `yaml:"prefix,omitempty"`
	Path   string `yaml:"path,omitempty"`
}

// SBOM is the top-level sbom block.
type SBOM struct {
	Format         string          `yaml:"format"`        // cyclonedx | spdx
	SpecVersion    string          `yaml:"spec_version"`  // e.g., "1.5"
	EmitPerBuild   bool            `yaml:"emit_per_build"`
	Destination    SBOMDestination `yaml:"destination"`
	RetentionDays  int             `yaml:"retention_days"`
}

// BannedPackage identifies a package banned by governance/CVE policy.
type BannedPackage struct {
	Ecosystem    Ecosystem `yaml:"ecosystem"`
	Name         string    `yaml:"name"`
	VersionGlob  string    `yaml:"version_glob,omitempty"`
	Reason       string    `yaml:"reason,omitempty"`
}

// Provenance is the signature verification policy block.
type Provenance struct {
	Enabled            bool     `yaml:"enabled"`
	Signer             string   `yaml:"signer"` // cosign | sigstore | gpg
	RequiredFor        []string `yaml:"required_for,omitempty"`
	AllowFailureModes  []string `yaml:"allow_failure_modes,omitempty"`
}

// Policy is the top-level supply-chain policy.
type Policy struct {
	Version          int             `yaml:"version"`
	DepPinning       DepPinning      `yaml:"dep_pinning"`
	SBOM             SBOM            `yaml:"sbom"`
	LicenseAllowlist []string        `yaml:"license_allowlist"`
	BannedPackages   []BannedPackage `yaml:"banned_packages"`
	Provenance       Provenance      `yaml:"provenance"`
}

// Errors.
var (
	ErrInvalidPolicy         = errors.New("supply_chain: invalid policy")
	ErrUnsupportedVersion    = errors.New("supply_chain: unsupported policy version")
	ErrUnknownYAMLKey        = errors.New("supply_chain: unknown YAML key (strict mode)")
	ErrLicenseNotAllowed     = errors.New("supply_chain: license not in allowlist")
	ErrPackageBanned         = errors.New("supply_chain: package is banned by policy")
	ErrSignatureUnverified   = errors.New("supply_chain: artifact signature could not be verified")
	ErrProvenanceUnsupported = errors.New("supply_chain: provenance signer not supported")
)

// LoadAndValidate reads + parses policy.yaml.
func LoadAndValidate(path string, mode LoadMode) (Policy, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return Policy{}, fmt.Errorf("supply_chain: read policy: %w", err)
	}
	return ParseAndValidate(raw, mode)
}

// ParseAndValidate is LoadAndValidate without the file read.
func ParseAndValidate(raw []byte, mode LoadMode) (Policy, error) {
	var p Policy
	dec := yaml.NewDecoder(bytes.NewReader(raw))
	if mode == ModeStrict {
		dec.KnownFields(true)
	}
	if err := dec.Decode(&p); err != nil {
		if mode == ModeStrict && (strings.Contains(err.Error(), "not found in type") || strings.Contains(err.Error(), "field ")) {
			return Policy{}, fmt.Errorf("%w: %v", ErrUnknownYAMLKey, err)
		}
		return Policy{}, fmt.Errorf("supply_chain: yaml unmarshal: %w", err)
	}
	if err := p.Validate(); err != nil {
		return Policy{}, err
	}
	return p, nil
}

// Validate inspects the loaded policy for required fields + sane values.
func (p Policy) Validate() error {
	if p.Version != 1 {
		return fmt.Errorf("%w: %d (expected 1)", ErrUnsupportedVersion, p.Version)
	}
	if len(p.DepPinning.Ecosystems) == 0 {
		return fmt.Errorf("%w: dep_pinning.ecosystems empty", ErrInvalidPolicy)
	}
	seenEcos := make(map[Ecosystem]struct{}, len(p.DepPinning.Ecosystems))
	for _, e := range p.DepPinning.Ecosystems {
		switch e.Ecosystem {
		case EcosystemGo, EcosystemRust, EcosystemPython, EcosystemJS, EcosystemDocker:
		default:
			return fmt.Errorf("%w: dep_pinning ecosystem=%q unknown", ErrInvalidPolicy, e.Ecosystem)
		}
		if _, dup := seenEcos[e.Ecosystem]; dup {
			return fmt.Errorf("%w: dep_pinning duplicate ecosystem=%q", ErrInvalidPolicy, e.Ecosystem)
		}
		seenEcos[e.Ecosystem] = struct{}{}
		// Docker is allowed to have neither lockfile nor lockfile_options
		// (it's a non-package ecosystem). All others MUST declare at
		// least one of the two fields.
		if e.Ecosystem != EcosystemDocker {
			if e.Lockfile == "" && len(e.LockfileOptions) == 0 {
				return fmt.Errorf("%w: ecosystem=%q has no lockfile or lockfile_options", ErrInvalidPolicy, e.Ecosystem)
			}
		}
		if e.Lockfile != "" && len(e.LockfileOptions) > 0 {
			return fmt.Errorf("%w: ecosystem=%q has both lockfile and lockfile_options (pick one)", ErrInvalidPolicy, e.Ecosystem)
		}
	}
	switch p.SBOM.Format {
	case "cyclonedx", "spdx":
	default:
		return fmt.Errorf("%w: sbom.format=%q must be cyclonedx|spdx", ErrInvalidPolicy, p.SBOM.Format)
	}
	if strings.TrimSpace(p.SBOM.SpecVersion) == "" {
		return fmt.Errorf("%w: sbom.spec_version empty", ErrInvalidPolicy)
	}
	if p.SBOM.RetentionDays <= 0 {
		return fmt.Errorf("%w: sbom.retention_days must be > 0", ErrInvalidPolicy)
	}
	if p.Provenance.Enabled {
		switch p.Provenance.Signer {
		case "cosign", "sigstore", "gpg":
		default:
			return fmt.Errorf("%w: %q", ErrProvenanceUnsupported, p.Provenance.Signer)
		}
	}
	return nil
}

// LicenseAllowed returns true if the SPDX license id is in the allowlist
// (case-sensitive — SPDX ids are case-sensitive per spec).
func (p Policy) LicenseAllowed(spdxID string) bool {
	for _, l := range p.LicenseAllowlist {
		if l == spdxID {
			return true
		}
	}
	return false
}

// CheckPackage returns ErrPackageBanned if (ecosystem, name) is on the
// banned list, nil otherwise. Version-glob matching is exact (TODO:
// fnmatch in cycle 21).
func (p Policy) CheckPackage(eco Ecosystem, name, version string) error {
	for _, b := range p.BannedPackages {
		if b.Ecosystem != eco {
			continue
		}
		if b.Name != name {
			continue
		}
		if b.VersionGlob == "" || b.VersionGlob == "*" || b.VersionGlob == version {
			return fmt.Errorf("%w: %s/%s@%s reason=%q", ErrPackageBanned, eco, name, version, b.Reason)
		}
	}
	return nil
}
