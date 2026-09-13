# Rollback — how to undo a release, and when you cannot

Reconciles: Versioning & Releases · Non-Vacuity — this adds no policy. What a release IS, and what
its artifacts are, come from that row; this says how to reverse one, and NV-6 is why the procedure
below was exercised rather than described.

**Written 2026-09-13** against AC-12 of `docs/plans/2026-09-13-v0.1.0-ship-acceptance.md`, which
was `❓ unknown` because nobody had asked. It is now asked.

## 1. What a rollback actually is here

A release is a pushed `vX.Y.Z` tag. `oss-release.yml` builds **33** service images, pushes them to
`ghcr.io/<owner>/<service>:vX.Y.Z` (plus `:latest` for a full release), and publishes a GitHub
Release. **Nothing is deleted or mutated**, so rolling back is redeploying the previous tag, not
undoing anything.

```bash
# per service, or across the compose file
docker pull  ghcr.io/<owner>/<service>:<previous-version>
docker tag   ghcr.io/<owner>/<service>:<previous-version> <service>:current
# then restart that service only
docker compose -p <project> -f docker-compose.yml up -d --no-deps <service>
```

A pre-release never moves `:latest`, so `docker pull <service>:latest` cannot land on unfinished
work — which means for a pre-release there is usually nothing to roll back on that tag at all.

## 2. The part that decides whether rollback is SAFE — the schema

**Images roll back. Databases do not.** The novel-platform services do not use versioned
up/down migrations: each runs an idempotent `CREATE TABLE IF NOT EXISTS` DDL blob at startup
(`services/*/app/db/migrate.py`, six of them). There is **no down path at all**. Schema only moves
forward.

That blob is cumulative and it does contain non-additive statements — `RENAME COLUMN
max_spend_usd TO max_spend_tokens`, `RENAME COLUMN language TO original_language`, `DROP TABLE IF
EXISTS source_corpus` and others. An older image meeting a renamed column or a dropped table will
fail, and no rollback of the image fixes that.

*(The foundation/game track is different and better off: `contracts/migrations/` has **73 up and 73
down**, exact parity, so it is reversible on its own terms.)*

**So the question before every rollback is one command, not a judgement:**

```bash
git diff --name-only <previous-tag> <this-release> -- '*/db/migrate.py' '*/migrations/*' '*.sql'
```

- **Empty** → the schema is identical; redeploying the old images is safe.
- **Non-empty** → READ the diff. Anything that renames, drops, or adds a `NOT NULL` without a
  default is **not rollback-safe**, and the recovery is forward-fix, not rollback.

**For v0.1.0 specifically, that command returns nothing.** Zero schema-touching files changed
between `v0.1.0-rc.1` and `main`, so this release is rollback-safe by that test.

## 3. Exercised, not asserted

Two genuinely different frontend images were built — one carrying react-router 7, one carrying 6 —
and a live container was moved between them. Distinct images, confirmed by bundle digest rather
than by tag:

```
v0.1.0       imageid=fab6749bb8d5  bundle_md5=54d1ab7df36670242393137926574e96
v0.1.0-rc.1  imageid=1b9f16affabb  bundle_md5=2037cf2968e93b7812ca0eb6a56c2c6f
```

```
1. DEPLOY   v0.1.0       -> HTTP=200  [Up]
2. ROLLBACK v0.1.0-rc.1  -> HTTP=200  [Up]
3. FORWARD  v0.1.0       -> HTTP=200  [Up]
```

**One real gotcha, found by hitting it.** Run outside its compose network the container dies at
once: `nginx: [emerg] host not found in upstream "api-gateway-bff"`. A rollback that starts a
container detached from the network looks like a broken image and is not one — attach it to the
project network.

## 4. What this does NOT establish

- **One service, not 33.** The mechanism is identical for every image, but only the frontend was
  moved. A full-stack rollback has ordering concerns this does not touch.
- **No data was written across the boundary.** Rolling back with in-flight writes, or with rows an
  older reader cannot parse, is a different question.
- **No production target exists to rehearse against.** This ran against the local `infra` stack.
