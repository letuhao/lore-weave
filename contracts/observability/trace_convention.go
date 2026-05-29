package observability

import "regexp"

// traceSpanRE pins the SR12 §12AO §4 trace-span naming convention:
//
//	<service>.<operation>(.<phase>)?
//
// where each segment is snake_case ([a-z][a-z0-9_]*) and segments are
// dot-separated. Examples:
//
//	publisher.xadd
//	world.provision.canary_run
//	roleplay.session.heartbeat
var traceSpanRE = regexp.MustCompile(`^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`)
