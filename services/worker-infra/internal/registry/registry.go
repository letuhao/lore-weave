package registry

import (
	"context"
	"fmt"
	"log/slog"
	"sync"
)

type Registry struct {
	tasks map[string]Task
}

func New() *Registry {
	return &Registry{tasks: make(map[string]Task)}
}

func (r *Registry) Register(task Task) {
	r.tasks[task.Name()] = task
}

// RunSelected starts each named task in a goroutine and blocks until ctx is cancelled.
// Returns the first non-nil error from any task, or nil if all shut down cleanly.
func (r *Registry) RunSelected(ctx context.Context, names []string) error {
	if len(names) == 0 {
		return fmt.Errorf("no tasks selected — set WORKER_TASKS env")
	}

	var wg sync.WaitGroup
	errCh := make(chan error, len(names))

	for _, name := range names {
		task, ok := r.tasks[name]
		if !ok {
			return fmt.Errorf("unknown task: %q", name)
		}
		wg.Add(1)
		go func(t Task) {
			defer wg.Done()
			slog.Info("starting task", "task", t.Name())
			if err := t.Run(ctx); err != nil {
				slog.Error("task exited with error", "task", t.Name(), "error", err)
				errCh <- err
			} else {
				slog.Info("task stopped", "task", t.Name())
			}
		}(task)
	}

	wg.Wait()
	close(errCh)

	for err := range errCh {
		if err != nil {
			return err
		}
	}
	return nil
}
