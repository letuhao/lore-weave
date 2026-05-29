// services/meta-worker/cmd/meta-worker — entry point for the L2.L
// sole xreality consumer.
//
// V1 SKELETON: wires the in-process skeleton dispatcher + validates the
// I7 ALLOWLIST invariant + prints a banner + exits cleanly. Production
// wiring (Redis Streams XREADGROUP + graceful shutdown) lands in cycle
// 11/L4 when the live stack is bootable.

package main

import (
	"fmt"
	"os"

	"github.com/loreweave/foundation/services/meta-worker/pkg/dispatch"
)

const banner = `
[meta-worker] L2.L sole xreality consumer — V1 skeleton
[meta-worker] I7 invariant: only this service consumes xreality.* topics
[meta-worker] Production wiring lands cycle 11/L4 (redis XREADGROUP + ticker)
`

func main() {
	fmt.Print(banner)

	sink := &dispatch.SkeletonSink{}
	d := dispatch.NewWithSkeletons(sink)
	if err := d.ValidateAllowlist(); err != nil {
		fmt.Fprintf(os.Stderr, "[meta-worker] FATAL: I7 ALLOWLIST violated: %v\n", err)
		os.Exit(2)
	}

	fmt.Printf("[meta-worker] dispatcher: %d xreality handlers registered\n", len(d.Registered()))
	for _, et := range d.Registered() {
		fmt.Printf("[meta-worker]   handler: %s\n", et)
	}
	fmt.Println("[meta-worker] skeleton OK — exit 0 (wire-in deferred to cycle 11/L4)")
}
