"""Storage adapters — one implementation of a port per backend (plan Phase 2).

⚠️ **`app/db/neo4j_repos/` is also adapter territory, and T16's gate must say so.**
That package predates this naming: it is already "the Neo4j implementation", complete with
the tenancy helpers that make its queries safe. The adapters here delegate to it rather
than copying its Cypher — a byte-for-byte duplicate would be two places to fix a tenant
filter, which is the failure mode `neo4j_repos` exists to prevent.

So T16's `no-cypher-outside-adapters` check must allow BOTH `app/adapters/` and
`app/db/neo4j_repos/`, or T17 must move the repos under `app/adapters/neo4j/`. Written
down here because a gate that silently allowlists a directory nobody remembers deciding on
is how an invariant becomes a formality.
"""
