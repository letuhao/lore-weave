package timeline

import "sync"

// newSyncMutex constructs the production lockable backed by sync.Mutex.
func newSyncMutex() lockable {
	return &syncMutex{}
}

type syncMutex struct {
	m sync.Mutex
}

func (s *syncMutex) Lock()   { s.m.Lock() }
func (s *syncMutex) Unlock() { s.m.Unlock() }
