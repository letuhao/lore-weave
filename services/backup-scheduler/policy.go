// Package backupscheduler — L1.H tiered backup policy loader + dispatcher
// contract. Cycle 7 ships the policy resolver; the live backup runner lands
// in a follow-on integration cycle (see README.md).
package backupscheduler

import (
	"errors"
	"fmt"
	"io"
	"os"
	"time"
)

// PolicyTier captures the per-status backup cadence + retention.
type PolicyTier struct {
	IncrementalInterval *time.Duration
	FullInterval        *time.Duration
	RetentionDays       int
	Compression         string
}

// Policy is the loaded contracts/backup/policy.yaml.
type Policy struct {
	Version      int
	TargetBucket string
	RestoreDrill RestoreDrillPolicy
	Tiers        map[string]PolicyTier
}

// RestoreDrillPolicy captures the Q-L1H-2 drill cadence.
type RestoreDrillPolicy struct {
	PerShardCadence     string // e.g., "monthly"
	PerShardAutomated   bool
	FullSystemCadence   string
	FullSystemAutomated bool
	AlertOnDrillFailure string // "page" | "warn"
}

// ErrPolicyInvalid is returned by LoadPolicy when the YAML is malformed or
// fails sanity checks (no default tier, retention <= 0, etc.).
var ErrPolicyInvalid = errors.New("backup-scheduler: policy invalid")

// LoadPolicy reads YAML from r. Pure-Go minimal yaml; we use a tiny parser
// over key:value lines because we don't want to pull yaml.v3 just for this.
//
// For broader use, the cycle that wires the actual runner can swap to
// gopkg.in/yaml.v3.
func LoadPolicy(r io.Reader) (*Policy, error) {
	data, err := io.ReadAll(r)
	if err != nil {
		return nil, fmt.Errorf("%w: read: %v", ErrPolicyInvalid, err)
	}
	return parsePolicyYAML(string(data))
}

// LoadPolicyFile is a convenience wrapper around LoadPolicy.
func LoadPolicyFile(path string) (*Policy, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("%w: open %s: %v", ErrPolicyInvalid, path, err)
	}
	defer f.Close()
	return LoadPolicy(f)
}

// TierFor returns the tier for the given reality status. Falls back to the
// `default` tier (with a non-nil error if no default exists in the policy).
func (p *Policy) TierFor(status string) (PolicyTier, error) {
	if t, ok := p.Tiers[status]; ok {
		return t, nil
	}
	if t, ok := p.Tiers["default"]; ok {
		return t, nil
	}
	return PolicyTier{}, fmt.Errorf("%w: no tier for status %q and no default", ErrPolicyInvalid, status)
}

// parsePolicyYAML is a minimal hand-rolled parser tuned for the
// contracts/backup/policy.yaml shape. Recognizes:
//   - version: <int>
//   - target_bucket: <name>
//   - restore_drill: { per_shard_cadence/per_shard_automated/full_system_cadence/full_system_automated/alert_on_drill_failure }
//   - tiers: { <status>: { incremental_interval/full_interval/retention_days/compression } }
//
// Refuses unknown top-level keys (defense against silent typos).
func parsePolicyYAML(body string) (*Policy, error) {
	p := &Policy{Tiers: make(map[string]PolicyTier)}
	type ctxKind int
	const (
		ctxTop ctxKind = iota
		ctxRestoreDrill
		ctxTiers
		ctxTierBody
	)
	curCtx := ctxTop
	curTierName := ""
	curTier := PolicyTier{}

	lines := splitLines(body)
	for i, raw := range lines {
		line := stripCommentTrim(raw)
		if line == "" {
			continue
		}
		indent := leadingSpaces(raw)
		key, val := splitKV(line)

		switch curCtx {
		case ctxTop:
			if indent != 0 {
				return nil, fmt.Errorf("%w: line %d unexpected indent: %q", ErrPolicyInvalid, i+1, raw)
			}
			switch key {
			case "version":
				p.Version = atoiOr(val, 0)
			case "target_bucket":
				p.TargetBucket = stripQuotes(val)
			case "restore_drill":
				curCtx = ctxRestoreDrill
			case "tiers":
				curCtx = ctxTiers
			default:
				return nil, fmt.Errorf("%w: line %d unknown top-level key %q", ErrPolicyInvalid, i+1, key)
			}
		case ctxRestoreDrill:
			if indent == 0 {
				// closed restore_drill; reprocess this line as top-level
				curCtx = ctxTop
				switch key {
				case "tiers":
					curCtx = ctxTiers
				case "version":
					p.Version = atoiOr(val, 0)
				case "target_bucket":
					p.TargetBucket = stripQuotes(val)
				default:
					return nil, fmt.Errorf("%w: line %d unknown top-level key %q", ErrPolicyInvalid, i+1, key)
				}
				continue
			}
			switch key {
			case "per_shard_cadence":
				p.RestoreDrill.PerShardCadence = stripQuotes(val)
			case "per_shard_automated":
				p.RestoreDrill.PerShardAutomated = val == "true"
			case "full_system_cadence":
				p.RestoreDrill.FullSystemCadence = stripQuotes(val)
			case "full_system_automated":
				p.RestoreDrill.FullSystemAutomated = val == "true"
			case "alert_on_drill_failure":
				p.RestoreDrill.AlertOnDrillFailure = stripQuotes(val)
			}
		case ctxTiers:
			if indent == 0 {
				// closed tiers; ignore (last block)
				curCtx = ctxTop
				continue
			}
			if indent == 2 && val == "" {
				// `<name>:` — new tier
				curTierName = stripQuotes(key)
				curTier = PolicyTier{Compression: "zstd", RetentionDays: 14}
				curCtx = ctxTierBody
			}
		case ctxTierBody:
			if indent == 0 {
				if curTierName != "" {
					p.Tiers[curTierName] = curTier
				}
				curTierName = ""
				curCtx = ctxTop
				// Reprocess
				switch key {
				case "version":
					p.Version = atoiOr(val, 0)
				case "target_bucket":
					p.TargetBucket = stripQuotes(val)
				case "restore_drill":
					curCtx = ctxRestoreDrill
				case "tiers":
					curCtx = ctxTiers
				}
				continue
			}
			if indent == 2 && val == "" {
				// flush previous tier, start new
				if curTierName != "" {
					p.Tiers[curTierName] = curTier
				}
				curTierName = stripQuotes(key)
				curTier = PolicyTier{Compression: "zstd", RetentionDays: 14}
				continue
			}
			// indent >= 4 — field of current tier
			switch key {
			case "incremental_interval":
				curTier.IncrementalInterval = parseDurationPtrOrNull(val)
			case "full_interval":
				curTier.FullInterval = parseDurationPtrOrNull(val)
			case "retention_days":
				curTier.RetentionDays = atoiOr(val, 0)
			case "compression":
				curTier.Compression = stripQuotes(val)
			}
		}
	}
	if curTierName != "" {
		p.Tiers[curTierName] = curTier
	}

	if p.Version == 0 {
		return nil, fmt.Errorf("%w: missing version", ErrPolicyInvalid)
	}
	if p.TargetBucket == "" {
		return nil, fmt.Errorf("%w: missing target_bucket", ErrPolicyInvalid)
	}
	if _, ok := p.Tiers["default"]; !ok {
		return nil, fmt.Errorf("%w: tiers.default required", ErrPolicyInvalid)
	}
	for status, t := range p.Tiers {
		if t.RetentionDays <= 0 {
			return nil, fmt.Errorf("%w: tier %q retention_days must be > 0", ErrPolicyInvalid, status)
		}
	}
	return p, nil
}

func parseDurationPtrOrNull(s string) *time.Duration {
	if s == "null" || s == "~" || s == "" {
		return nil
	}
	d, err := time.ParseDuration(s)
	if err != nil {
		return nil
	}
	return &d
}

func atoiOr(s string, def int) int {
	if s == "" {
		return def
	}
	n := 0
	neg := false
	i := 0
	if s[0] == '-' {
		neg = true
		i = 1
	}
	for ; i < len(s); i++ {
		c := s[i]
		if c < '0' || c > '9' {
			return def
		}
		n = n*10 + int(c-'0')
	}
	if neg {
		return -n
	}
	return n
}

func stripQuotes(s string) string {
	if len(s) >= 2 {
		if (s[0] == '"' && s[len(s)-1] == '"') || (s[0] == '\'' && s[len(s)-1] == '\'') {
			return s[1 : len(s)-1]
		}
	}
	return s
}

func splitLines(s string) []string {
	out := []string{}
	cur := ""
	for _, r := range s {
		if r == '\n' {
			out = append(out, cur)
			cur = ""
			continue
		}
		cur += string(r)
	}
	out = append(out, cur)
	return out
}

func stripCommentTrim(line string) string {
	for i := 0; i < len(line); i++ {
		if line[i] == '#' {
			line = line[:i]
			break
		}
	}
	out := ""
	end := len(line)
	for end > 0 && (line[end-1] == ' ' || line[end-1] == '\t' || line[end-1] == '\r') {
		end--
	}
	line = line[:end]
	start := 0
	for start < len(line) && (line[start] == ' ' || line[start] == '\t') {
		start++
	}
	out = line[start:]
	return out
}

func leadingSpaces(line string) int {
	n := 0
	for n < len(line) && line[n] == ' ' {
		n++
	}
	return n
}

func splitKV(line string) (string, string) {
	for i := 0; i < len(line); i++ {
		if line[i] == ':' {
			k := line[:i]
			v := ""
			if i+1 < len(line) {
				v = line[i+1:]
			}
			// trim v leading spaces
			for len(v) > 0 && v[0] == ' ' {
				v = v[1:]
			}
			return k, v
		}
	}
	return line, ""
}
