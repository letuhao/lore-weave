"""Storage ports (plan Phase 2).

A port is the vocabulary the domain uses to talk to storage: domain operations, never
queries. The adapters under `app/adapters/` implement them — one per backend — and a fake
implements each port in memory so the ~561 tests that needed a live Neo4j can stop needing
one (T20).

The rule that makes this worth doing: a consumer must not be able to tell WHICH adapter
answered. Anything a caller can only get from Neo4j (a Cypher string, a driver session, a
`neo4j.time` value) does not belong in a port signature.
"""
