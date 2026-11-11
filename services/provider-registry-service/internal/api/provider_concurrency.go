package api

import (
	"context"

	"github.com/loreweave/provider-registry-service/internal/ratelimit"
)

func (s *Server) acquireProviderSlot(waitCtx, callCtx context.Context, credentialID string, limit int) (ratelimit.ProviderPermit, error) {
	if limit <= 0 {
		limit = s.providerDefaultMax
	}
	if limit <= 0 {
		limit = 8
	}
	if s.providerAcquireTimeout > 0 {
		var cancel context.CancelFunc
		waitCtx, cancel = context.WithTimeout(waitCtx, s.providerAcquireTimeout)
		defer cancel()
	}
	if s.providerGovernor == nil {
		return nil, ratelimit.ErrGovernorUnavailable
	}
	return s.providerGovernor.Acquire(waitCtx, callCtx, credentialID, limit)
}

var _ ratelimit.ConcurrencyGovernor = (*ratelimit.LocalGovernor)(nil)
