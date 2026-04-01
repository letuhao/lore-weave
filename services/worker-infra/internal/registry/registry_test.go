package registry

import (
	"context"
	"testing"
	"time"
)

type fakeTask struct {
	name string
	ran  bool
}

func (f *fakeTask) Name() string { return f.name }
func (f *fakeTask) Run(ctx context.Context) error {
	f.ran = true
	<-ctx.Done()
	return nil
}

func TestRegistryRunSelected(t *testing.T) {
	r := New()
	task := &fakeTask{name: "test-task"}
	r.Register(task)

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	err := r.RunSelected(ctx, []string{"test-task"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !task.ran {
		t.Fatal("expected task to have run")
	}
}

func TestRegistryUnknownTask(t *testing.T) {
	r := New()
	err := r.RunSelected(context.Background(), []string{"nope"})
	if err == nil {
		t.Fatal("expected error for unknown task")
	}
}

func TestRegistryNoTasks(t *testing.T) {
	r := New()
	err := r.RunSelected(context.Background(), nil)
	if err == nil {
		t.Fatal("expected error for empty task list")
	}
}
