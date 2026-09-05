"""Neo4j repository layer (K11.5+).

Every Cypher query in this package MUST go through the K11.4
`run_read` / `run_write` helpers in `app.db.neo4j_helpers`. The
`assert_user_id_param` runtime check is the multi-tenant safety
net — bypassing it via a direct `session.run(...)` call is the
single highest-severity bug class in this service.

The one documented exception is `app.db.neo4j_schema`, which
applies the global schema (constraints + indexes + vector
indexes) on startup. See its module docstring for why.
"""
