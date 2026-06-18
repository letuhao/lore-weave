package service_acl

import (
	"errors"
	"fmt"
	"io"
	"strings"

	"gopkg.in/yaml.v3"
)

// PrincipalMode is the S11 §12AA enumeration: a per-RPC declaration of
// whether the caller MUST be acting on behalf of a user, MAY only be a
// system actor, or EITHER is acceptable.
type PrincipalMode string

const (
	// PrincipalRequiresUser — the RPC handler refuses calls without a
	// user_ref_id (e.g., user-scoped reads / writes). audit row carries
	// the user_ref_id and the constraint
	// s2s_audit_user_ref_present_when_required (migration 016) is
	// load-bearing.
	PrincipalRequiresUser PrincipalMode = "requires_user"
	// PrincipalSystemOnly — internal scheduler / orchestrator path; user
	// context is forbidden (set to nil). Example: archive-worker DROP
	// partition.
	PrincipalSystemOnly PrincipalMode = "system_only"
	// PrincipalEither — informational RPC (e.g., catalog read) callable
	// with or without a user context.
	PrincipalEither PrincipalMode = "either"
)

// IsValid returns true if the PrincipalMode is one of the three known
// values. Empty string returns false (callers must set explicitly).
func (p PrincipalMode) IsValid() bool {
	switch p {
	case PrincipalRequiresUser, PrincipalSystemOnly, PrincipalEither:
		return true
	}
	return false
}

// Decision is the AllowDeny result returned by CheckRPCAllowed. Default
// zero value = DenyDefault (default-deny invariant — a programmer who
// forgets to populate the matrix gets a refused RPC, not an open RPC).
type Decision int

const (
	// DenyDefault — RPC was not in the matrix (the caller declared no
	// entry, or the rpc name was misspelled). Default-DENY invariant.
	DenyDefault Decision = iota
	// Allow — caller is in the allowed_callers set for the (callee, rpc).
	Allow
	// DenyCallerNotAllowed — RPC exists in matrix but caller not in
	// allowed_callers. Distinct from DenyDefault so dashboards can tell
	// "missing matrix row" (which the lint catches) from "active deny".
	DenyCallerNotAllowed
	// DenyPrincipalMismatch — RPC declares requires_user but the call
	// arrived without a user_ref_id (or system_only with one). The
	// middleware checks principal mode AFTER caller authz.
	DenyPrincipalMismatch
)

// String renders Decision for logs/audit.
func (d Decision) String() string {
	switch d {
	case DenyDefault:
		return "deny_default"
	case Allow:
		return "allow"
	case DenyCallerNotAllowed:
		return "deny_caller_not_allowed"
	case DenyPrincipalMismatch:
		return "deny_principal_mismatch"
	}
	return "deny_unknown"
}

// IsAllow returns true only for the Allow decision. All other values
// (including the zero-value DenyDefault) deny.
func (d Decision) IsAllow() bool { return d == Allow }

// RPCRule is a single per-RPC declaration on a callee service entry.
type RPCRule struct {
	// AllowedCallers is the set of caller service names permitted to
	// invoke this RPC. Empty slice = no callers allowed (defense in
	// depth against an accidentally-merged empty list).
	AllowedCallers []string `yaml:"allowed_callers"`
	// PrincipalMode (optional, defaults to PrincipalEither). When set,
	// the inbound middleware MUST verify that the call's principal
	// presence matches.
	PrincipalMode PrincipalMode `yaml:"principal_mode,omitempty"`
}

// ServiceEntry is a single entry in matrix.yaml. The original cycle-6
// shape (`permissions` keyed by table name) remains, additive: L4.M.1
// adds the optional `rpcs` map.
type ServiceEntry struct {
	Name          string                 `yaml:"name"`
	SVIDSpiffeID  string                 `yaml:"svid_spiffe_id"`
	Notes         string                 `yaml:"notes,omitempty"`
	Permissions   map[string][]string    `yaml:"permissions,omitempty"`
	RPCs          map[string]RPCRule     `yaml:"rpcs,omitempty"`
}

// Matrix is the parsed registry.
type Matrix struct {
	Version  int             `yaml:"version"`
	Services []ServiceEntry  `yaml:"services"`

	// by-callee-name lookup (built by LoadMatrix). callee → rpc → rule.
	rpcIndex map[string]map[string]RPCRule
}

// ErrInvalidMatrix is returned by LoadMatrix when the YAML is structurally
// wrong: missing version, duplicate service names, empty service name,
// empty allowed_callers, invalid principal_mode.
var ErrInvalidMatrix = errors.New("service_acl: invalid matrix")

// LoadMatrix parses a matrix.yaml from r. Validates structure + builds
// the rpcIndex for O(1) CheckRPCAllowed lookups. Returns ErrInvalidMatrix
// (wrapped) for any structural defect.
func LoadMatrix(r io.Reader) (*Matrix, error) {
	if r == nil {
		return nil, fmt.Errorf("%w: nil reader", ErrInvalidMatrix)
	}
	raw, err := io.ReadAll(r)
	if err != nil {
		return nil, fmt.Errorf("%w: read: %v", ErrInvalidMatrix, err)
	}
	var m Matrix
	if err := yaml.Unmarshal(raw, &m); err != nil {
		return nil, fmt.Errorf("%w: yaml: %v", ErrInvalidMatrix, err)
	}
	if m.Version < 1 {
		return nil, fmt.Errorf("%w: version must be >= 1 (got %d)", ErrInvalidMatrix, m.Version)
	}

	seen := make(map[string]struct{})
	m.rpcIndex = make(map[string]map[string]RPCRule)
	for i, svc := range m.Services {
		if strings.TrimSpace(svc.Name) == "" {
			return nil, fmt.Errorf("%w: service[%d] missing name", ErrInvalidMatrix, i)
		}
		if _, dup := seen[svc.Name]; dup {
			return nil, fmt.Errorf("%w: duplicate service name %q", ErrInvalidMatrix, svc.Name)
		}
		seen[svc.Name] = struct{}{}

		if len(svc.RPCs) == 0 {
			continue
		}
		rpcMap := make(map[string]RPCRule, len(svc.RPCs))
		for rpcName, rule := range svc.RPCs {
			if strings.TrimSpace(rpcName) == "" {
				return nil, fmt.Errorf("%w: service %q has empty rpc name", ErrInvalidMatrix, svc.Name)
			}
			if len(rule.AllowedCallers) == 0 {
				return nil, fmt.Errorf("%w: service %q rpc %q has empty allowed_callers (use [] explicitly is not allowed — omit the rpc instead)", ErrInvalidMatrix, svc.Name, rpcName)
			}
			for _, caller := range rule.AllowedCallers {
				if strings.TrimSpace(caller) == "" {
					return nil, fmt.Errorf("%w: service %q rpc %q has empty caller", ErrInvalidMatrix, svc.Name, rpcName)
				}
			}
			if rule.PrincipalMode != "" && !rule.PrincipalMode.IsValid() {
				return nil, fmt.Errorf("%w: service %q rpc %q invalid principal_mode %q", ErrInvalidMatrix, svc.Name, rpcName, rule.PrincipalMode)
			}
			rpcMap[rpcName] = rule
		}
		m.rpcIndex[svc.Name] = rpcMap
	}
	return &m, nil
}

// FindService returns the matching ServiceEntry by name, or (nil, false).
// O(N) over the slice; matrices are small (<200 services target).
func (m *Matrix) FindService(name string) (*ServiceEntry, bool) {
	if m == nil {
		return nil, false
	}
	for i := range m.Services {
		if m.Services[i].Name == name {
			return &m.Services[i], true
		}
	}
	return nil, false
}

// CheckRPCAllowed is the runtime authorization gate. Returns the Decision
// AND the matched RPCRule (zero-value when Decision != Allow). The
// inbound middleware uses (rule, decision) to drive both the
// allow/deny response and the audit row.
//
// Semantics:
//   - callee not in matrix       → DenyDefault
//   - callee has no `rpcs` map   → DenyDefault (cycle-6 services that
//                                  declared only `permissions:` table grants
//                                  are not RPC-callable yet; lint-flag the
//                                  service to add the rpcs map before any
//                                  service-to-service RPC ships).
//   - rpc not in callee's rpcs   → DenyDefault
//   - rpc rule present, caller in allowed_callers          → Allow
//   - rpc rule present, caller NOT in allowed_callers      → DenyCallerNotAllowed
//
// PrincipalMode is NOT checked here — the inbound middleware checks it
// after CheckRPCAllowed because the user_ref_id is bound to the request
// context, not the matrix.
func (m *Matrix) CheckRPCAllowed(caller, callee, rpc string) (Decision, RPCRule) {
	if m == nil || m.rpcIndex == nil {
		return DenyDefault, RPCRule{}
	}
	if caller == "" || callee == "" || rpc == "" {
		return DenyDefault, RPCRule{}
	}
	rpcMap, ok := m.rpcIndex[callee]
	if !ok {
		return DenyDefault, RPCRule{}
	}
	rule, ok := rpcMap[rpc]
	if !ok {
		return DenyDefault, RPCRule{}
	}
	for _, allowed := range rule.AllowedCallers {
		if allowed == caller {
			return Allow, rule
		}
	}
	return DenyCallerNotAllowed, rule
}

// CheckPrincipalAllowed verifies the principal mode of a request against
// the matched rule. Call this AFTER CheckRPCAllowed returned Allow.
//
// hasUser is true if the request carries a non-nil user_ref_id.
func (rule RPCRule) CheckPrincipalAllowed(hasUser bool) Decision {
	switch rule.PrincipalMode {
	case PrincipalRequiresUser:
		if !hasUser {
			return DenyPrincipalMismatch
		}
	case PrincipalSystemOnly:
		if hasUser {
			return DenyPrincipalMismatch
		}
	case PrincipalEither, "":
		// either accepts both
	default:
		return DenyPrincipalMismatch
	}
	return Allow
}
