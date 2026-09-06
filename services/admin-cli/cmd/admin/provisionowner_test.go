package main

// `W7-SHELL-UNCOVERED`'s last uncovered piece: the nil-owner guard in
// `buildProvisionRealityHandler`.
//
// # Why the guard exists, and why it needs a test rather than a reading
//
// `owner_user_id` is OPTIONAL — absent means the platform owns the reality
// (`owner_kind=system`). The nil UUID parses perfectly well, and one layer down
// the invoker DROPS the flag when the value is `uuid.Nil`. So an operator who
// typed `--owner-user-id 00000000-0000-0000-0000-000000000000` would get a
// **platform-owned reality and a success message**: the failure mode is a
// silent tenancy downgrade, reported as success, which is the shape no amount
// of reading a diff reliably catches.
//
// # What the second test is for
//
// `NV-2`: a guard's subject must be able to vary. A test that only feeds the
// nil UUID proves the handler errors on nil — it does NOT prove the *guard* is
// what errored, because the handler errors for several reasons. The second case
// feeds a REAL owner and asserts the failure is something else entirely, so the
// pair brackets the guard rather than resting on one side of it.
//
// Neither case reaches a database: the nil case returns at the guard, and the
// valid case fails in the subprocess invoker, which is why `PROVISION_BIN_PATH`
// points at a name that does not exist.

import (
	"context"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/admin-cli/internal/framework"
)

// Enough env for `ProvisionWorkerEnv.Validate` to pass. None of it is dialled:
// the handler must refuse the nil owner before any connection is attempted, and
// a test that needed a live meta database to prove that would be proving
// something else.
func configureProvisionEnv(t *testing.T) {
	t.Helper()
	for k, v := range map[string]string{
		"PROVISION_META_DSN":        "postgres://unused/meta",
		"PROVISION_SHARD_ADMIN_DSN": "postgres://unused/shard",
		"PROVISION_BRIDGE_URL":      "http://unused.invalid",
		"PROVISION_BRIDGE_TOKEN":    "unused",
		"PROVISION_SHARD_HOSTPORT":  "unused:5432",
		"PROVISION_PG_USER":         "unused",
		"PROVISION_BIN_PATH":        "provision-binary-that-does-not-exist",
	} {
		t.Setenv(k, v)
	}
}

func provisionHandler(t *testing.T) framework.Handler {
	t.Helper()
	configureProvisionEnv(t)
	h, cleanup, err := buildProvisionRealityHandler()
	if err != nil {
		t.Fatalf("buildProvisionRealityHandler: %v", err)
	}
	if cleanup != nil {
		t.Cleanup(cleanup)
	}
	if h == nil {
		t.Fatal("handler is nil — the env above was supposed to make it configured, so this " +
			"test would otherwise assert nothing")
	}
	return h
}

func TestProvisionHandler_RefusesTheNilOwnerUUID(t *testing.T) {
	h := provisionHandler(t)

	_, err := h(context.Background(), framework.Invocation{
		Params: map[string]string{
			"reality_id":    uuid.New().String(),
			"deploy_cohort": "0",
			"owner_user_id": uuid.Nil.String(),
		},
	})
	if err == nil {
		t.Fatal("the nil owner UUID was ACCEPTED — the operator would get a platform-owned " +
			"reality and a success message, which is a silent tenancy downgrade")
	}
	if !strings.Contains(err.Error(), "must not be the nil UUID") {
		t.Fatalf("errored, but not at the nil-owner guard: %v", err)
	}
}

func TestProvisionHandler_AcceptsARealOwnerPastTheGuard(t *testing.T) {
	h := provisionHandler(t)

	_, err := h(context.Background(), framework.Invocation{
		Params: map[string]string{
			"reality_id":    uuid.New().String(),
			"deploy_cohort": "0",
			"owner_user_id": uuid.New().String(),
		},
	})
	// It MUST fail — `PROVISION_BIN_PATH` names a binary that does not exist —
	// but it must fail somewhere other than the guard. If this ever reports the
	// nil-UUID message, the guard has started refusing every owner and the test
	// above would still be green.
	if err != nil && strings.Contains(err.Error(), "must not be the nil UUID") {
		t.Fatalf("a REAL owner uuid was refused by the nil-owner guard: %v", err)
	}
}
