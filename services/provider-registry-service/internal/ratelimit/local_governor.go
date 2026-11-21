package ratelimit

import (
	"context"
	"sync"
	"time"
)

type localSlot struct {
	inFlight int
	waiters  int
	changed  chan struct{}
}

type LocalGovernor struct {
	mu             sync.Mutex
	slots          map[string]*localSlot
	acquireTimeout time.Duration
}

func NewLocalGovernor(timeout ...time.Duration) *LocalGovernor {
	wait := 30 * time.Second
	if len(timeout) > 0 && timeout[0] > 0 {
		wait = timeout[0]
	}
	return &LocalGovernor{slots: map[string]*localSlot{}, acquireTimeout: wait}
}

func (g *LocalGovernor) Acquire(waitCtx, callCtx context.Context, class string, limit int) (ProviderPermit, error) {
	if callCtx == nil {
		callCtx = waitCtx
	}
	if limit <= 0 {
		return newNoopPermit(callCtx), nil
	}
	if g.acquireTimeout > 0 {
		var cancel context.CancelFunc
		waitCtx, cancel = context.WithTimeout(waitCtx, g.acquireTimeout)
		defer cancel()
	}
	g.mu.Lock()
	slot := g.slots[class]
	if slot == nil {
		slot = &localSlot{changed: make(chan struct{})}
		g.slots[class] = slot
	}
	slot.waiters++
	g.mu.Unlock()
	for {
		if err := waitCtx.Err(); err != nil {
			g.removeWaiter(class, slot)
			return nil, err
		}
		g.mu.Lock()
		if slot.inFlight < limit {
			slot.waiters--
			slot.inFlight++
			g.mu.Unlock()
			permitCtx, cancel := context.WithCancelCause(callCtx)

			var once sync.Once
			return newPermit(permitCtx, cancel, func() {
				once.Do(func() {
					g.mu.Lock()
					slot.inFlight--
					close(slot.changed)
					slot.changed = make(chan struct{})
					g.deleteIfIdle(class, slot)
					g.mu.Unlock()
				})
			}), nil
		}
		changed := slot.changed
		g.mu.Unlock()
		select {
		case <-waitCtx.Done():
			g.removeWaiter(class, slot)
			return nil, waitCtx.Err()
		case <-changed:
		}
	}
}

func (g *LocalGovernor) removeWaiter(class string, slot *localSlot) {
	g.mu.Lock()
	slot.waiters--
	g.deleteIfIdle(class, slot)
	g.mu.Unlock()
}

func (g *LocalGovernor) deleteIfIdle(class string, slot *localSlot) {
	if slot.inFlight == 0 && slot.waiters == 0 && g.slots[class] == slot {
		delete(g.slots, class)
	}
}

type CompositeGovernor struct {
	shared ConcurrencyGovernor
	local  ConcurrencyGovernor
}

func NewCompositeGovernor(shared, local ConcurrencyGovernor) *CompositeGovernor {
	return &CompositeGovernor{shared: shared, local: local}
}

func (g *CompositeGovernor) Acquire(waitCtx, callCtx context.Context, class string, limit int) (ProviderPermit, error) {
	if limit <= 0 {
		return newNoopPermit(callCtx), nil
	}
	if g == nil || g.shared == nil {
		return nil, ErrGovernorUnavailable
	}
	var localPermit ProviderPermit
	if g.local != nil {
		var err error
		localPermit, err = g.local.Acquire(waitCtx, callCtx, class, limit)
		if err != nil {
			return nil, err
		}
	}
	sharedPermit, err := g.shared.Acquire(waitCtx, callCtx, class, limit)
	if err != nil {
		if localPermit != nil {
			localPermit.Release()
		}
		return nil, err
	}
	permitCtx, cancel := context.WithCancelCause(callCtx)
	done, watcherDone := make(chan struct{}), make(chan struct{})
	go func() {
		defer close(watcherDone)
		select {
		case <-done:
		case <-permitCtx.Done():
		case <-sharedPermit.Context().Done():
			cause := context.Cause(sharedPermit.Context())
			if cause == nil {
				cause = ErrLeaseLost
			}
			cancel(cause)
		}
	}()
	var once sync.Once
	return newPermit(permitCtx, cancel, func() {
		once.Do(func() {
			close(done)
			sharedPermit.Release()
			<-watcherDone
			if localPermit != nil {
				localPermit.Release()
			}
		})
	}), nil
}
