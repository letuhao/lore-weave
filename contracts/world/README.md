# `contracts/world/` — authored world declarations

A world declaration is the `Vec<NodeDecl>` that
`world_service::world_seed::seed_world` writes, and that the provision path
carries as `ProvisionRequest.world`. It is **data an author edits**, never code.

## Why this directory exists

The space substrate got its producers before it had an author. Every in-repo
caller passed an **empty** declaration, so provision step 10
(`seed_world_structure`) reported `Skipped` on every path — the producer was
reachable and nothing exercised it. That was recorded as `OR-3` and this is its
answer.

## What a declaration is NOT

**Not a default.** Nothing here is applied to a reality unless a caller names it.
A structure every reality inherits that no author declared is the rot the
provision path already refuses — `ProvisionRequest.world` defaults to empty and
empty means *skipped*, never *use the starter map*.

## The rules a declaration must satisfy

`PF_001` §5, enforced by `world_seed::validate` before anything is written:

- exactly **one root** (`parent: null`); `0019`'s `channels_root_single` would
  refuse a second
- every parent exists, and the graph is **acyclic**
- depth ≤ **16** (`DP-Ch1`)
- containment follows the matrix (`SPG-A3`) — a `domain` may not hold a `world`
  unless the scale rule allows it, an `arena` holds nothing, and so on
- a `domain` **must** carry a `place`; anything else **must not** (both
  directions are rejections)
- `scale` is required for a `world` under a `domain` (`SDF-A19`)

## How they are kept honest

`services/world-service/tests/world_declarations.rs` loads **every** `*.json` in
this directory, deserialises it as `Vec<NodeDecl>` and runs `validate`. A
declaration that would be refused at seed time is refused in CI instead — a file
here that does not validate is a trap for whoever runs
`admin reality provision --world`.

## Using one

```bash
# provision a NEW reality with this world
admin reality provision --reality-id <uuid> --reason "..." \
  --world contracts/world/demo_v1.json
```
