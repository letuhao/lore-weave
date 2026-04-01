package registry

import "context"

// Task is the interface that all worker tasks must implement.
type Task interface {
	Name() string
	Run(ctx context.Context) error
}
