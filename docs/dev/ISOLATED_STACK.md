# The isolated local stack

A second, complete Compose stack that runs beside the normal one.

## Why

Two branches were working the same checkout against the same stack. `docker compose build
glossary-service` on either branch overwrote the **same image tag**, `up` replaced the
**same container**, and both wrote the **same databases**. Whoever ran last won, silently —
and a live smoke could measure the other branch's code without anything looking wrong.

This gives each branch its own everything.

## Use it

```bash
cd infra
./iso.sh up -d postgres redis neo4j glossary-service knowledge-service worker-infra
./iso.sh build knowledge-service
./iso.sh ps
./iso.sh logs -f knowledge-service
./iso.sh down            # containers only — the data survives
./iso.sh down -v         # ⚠️ destroys the isolated data too
```

PowerShell: `.\iso.ps1 …`, same arguments. Everything after the script name is passed
straight to `docker compose`.

**Always go through the wrapper.** The full command is
`docker compose -p lw-iso -f docker-compose.yml -f docker-compose.isolated.yml …`, and
dropping `-p lw-iso` does something much worse than failing: it applies the isolated
**port map** to the **shared project**, recreating the base stack's containers on shifted
ports against the base stack's volumes. The other branch's stack appears to vanish and its
data is being written by your services.

## What is isolated

| | Shared stack | Isolated stack |
|---|---|---|
| Compose project | `infra` | `lw-iso` |
| Containers | `infra-glossary-service-1` | `lw-iso-glossary-service-1` |
| Image tags | `infra-glossary-service` | `lw-iso-glossary-service` |
| Networks | `infra_default` | `lw-iso_default` |
| Volumes | `infra_loreweave_pg` | `lw-iso_loreweave_pg` |
| Host ports | as documented | **base + 20000** |

Everything. There is no shared surface between the two stacks — not the images, not the
databases, not the graph.

### Ports: add 20000

```
postgres            5555  ->  25555
redis               6399  ->  26399
neo4j (bolt)        7688  ->  27688
neo4j (browser)     7475  ->  27475
auth-service        8204  ->  28204
book-service        8205  ->  28205
glossary-service    8211  ->  28211
knowledge-service   8216  ->  28216
composition-service 8217  ->  28217
api-gateway-bff     3123  ->  23123
frontend            5174  ->  25174
```

Not +10000, which is the obvious choice: rabbitmq's management UI is already published on
15795 and `5795 + 10000` lands exactly on it. Every base port is below 20000, so a 20000
offset cannot collide.

Inside the stack nothing changes — services still reach each other as `postgres:5432`,
`glossary-service:8088`. The offset only affects what you type from the host.

## How it is built, and why there is no second compose file

`infra/docker-compose.isolated.yml` is **generated** and contains nothing but the port
remapping. The isolated stack *is* the base stack; change a service in
`docker-compose.yml` and both get it.

A copied 2172-line compose file would be a second source of truth: it would agree on the
day it was made and drift from then on, and nothing would notice. `CLAUDE.md` states the
rule this repo lives by — *one home, one name; guidance that is duplicated goes stale in
one copy and then actively misleads.* That applies to infrastructure too.

```bash
python infra/gen-isolated-compose.py           # regenerate after adding a published port
python infra/gen-isolated-compose.py --check   # reds if the base grew a port
```

`iso.sh` runs `--check` on every invocation and refuses to start against a stale map,
because a stale override leaves a new service publishing its **base** port — a collision
that reads as "the other stack is broken".

> `ports:` carries the `!override` YAML tag. Compose *concatenates* multi-value keys like
> `ports` across files, so without it the isolated stack would publish 5555 **and** 25555 —
> fighting the base stack for the very port the file exists to move.

## Data: the isolated stack starts empty

Own volumes means no books, no glossary, no graph. Every service migrates its schema on
boot and then sits there with nothing in it — correct, and useless for a live smoke.

```bash
./iso-seed.sh --list     # what would be cloned, and how big
./iso-seed.sh --pg       # clone auth + book + glossary + knowledge + composition
./iso-seed.sh --pg loreweave_book
```

The direction is one-way and enforced: **shared → isolated**. There is no flag to push the
other way; a seed script that can run backwards is one typo away from overwriting the
branch you were trying to protect.

### Neo4j is the awkward one

Community edition has no online backup, so a consistent copy needs the **source** stopped —
and the source is the stack the other branch is using. `./iso-seed.sh --neo4j` will do it
(stop, copy, start; ~30s) but asks first, and you should tell the other branch before
saying yes.

The alternative touches nothing shared. The glossary is the SSOT and the mirror repairer
exists, so the entity layer can be rebuilt inside the isolated stack from the cloned
glossary:

```bash
curl -X POST "http://localhost:28216/internal/projects/<project_id>/glossary-mirror-repair" \
     -H "X-Internal-Token: dev_internal_token"
```

That reconstructs every `:Entity`. It does **not** reconstruct relations or events — those
are extraction-derived and are not in the glossary. Measured on the acceptance book
2026-08-12, immediately after doing exactly this:

```
                    isolated (rebuilt)   shared (real)
:Entity                     43                47      <- 4 extraction-native, no glossary id
  with glossary id          43                43
relations                    0               101      <- the caveat, measured
```

A graph seeded that way is **entity-complete and edge-empty**. For the mirror work that is
the whole subject; for anything that reads relations — a canon check, a timeline — it is a
graph that will answer confidently and wrongly. Know which one your test needs, and if it
needs edges, use `--neo4j` and tell the other branch first.

> 🔴 **This warning did not save its own author.** On 2026-08-13 I counted `:EntityStatus`
> nodes here, read **zero**, and wrote in the plan that the canon liveness axis "cannot fire on
> ANY book in this corpus". The real graph holds **35** of them; this stack had none because
> **I built its graph from the glossary myself** and status nodes are extraction-derived.
>
> **Run CODE here. Measure DATA against the real stack.** A count taken in this stack is a
> count of what you cloned into it, which is a fact about your seeding and not about the
> product. The failure is silent: an empty result looks exactly like a finding.

## Memory

Measured 2026-08-12: the shared stack was 54 containers with **9.8 GB free of 95.7 GB**.
A second full stack does not fit. Start the services you need — dependencies come along
automatically:

```bash
./iso.sh up -d glossary-service knowledge-service worker-infra
# pulls in postgres, redis, neo4j, minio, rabbitmq, pandoc-server, book-service
```

`./iso.sh up -d` with no service names starts everything, and on this host it will not end
well.

## Merging back

The two stacks are infrastructure, not code — nothing here changes what either branch
builds. When the branches reconcile, this whole mechanism can stay: it costs nothing when
unused (`iso.sh down` leaves no running containers) and the next time two tracks overlap it
is already there.
