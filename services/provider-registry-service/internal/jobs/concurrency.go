package jobs

import (
	"context"
	"fmt"

	"github.com/google/uuid"
)

// EffectiveConcurrency resolves the class and positive defaulted cap shared by
// queue admission and per-call provider leases. maxConcurrency <= 0 means the
// configured runtime default applies (including platform models).
func (r *Repo) EffectiveConcurrency(
	ctx context.Context,
	modelSource string,
	ownerUserID, modelRef uuid.UUID,
	defaultLimit int,
) (key string, limit int, ok bool, err error) {
	key, limit, ok, err = r.ResolveConcurrency(ctx, modelSource, ownerUserID, modelRef)
	if err != nil || !ok {
		return key, limit, ok, err
	}
	if limit <= 0 {
		if defaultLimit <= 0 {
			return "", 0, false, fmt.Errorf("default provider concurrency limit must be positive")
		}
		limit = defaultLimit
	}
	return key, limit, true, nil
}
