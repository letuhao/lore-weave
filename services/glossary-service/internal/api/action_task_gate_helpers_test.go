package api

// asCard unwraps a KIND-C propose tool's now-`any` result back into the confirmCardOut
// it returns for a non-tasks client (every direct unit-test call passes req=nil ⇒ no
// ext-tasks capability ⇒ the confirm_token fallback). A tasks-capable client would get a
// task-handle map instead (exercised via the real /mcp handler in the DB-gated tests).
func asCard(out any) confirmCardOut {
	c, _ := out.(confirmCardOut)
	return c
}
