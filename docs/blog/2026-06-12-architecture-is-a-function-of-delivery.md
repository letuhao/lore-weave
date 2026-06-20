---
title: Architecture Is a Function of Your Delivery Model, Not Your Idea
published: false
description: My 25-container architecture wasn't a mistake — it was correct for the product I was building. Then one new idea quietly changed the delivery model underneath it.
tags: architecture, productdevelopment, softwareengineering, indiehackers
---

# Architecture Is a Function of Your Delivery Model, Not Your Idea

I'm a solo developer. My project runs an architecture I would happily defend in any design review:

- ~20 microservices across Go, Python, and TypeScript
- A database per service, the way the books say
- A transactional outbox feeding an event spine over Redis Streams
- RabbitMQ for job queues, MinIO for objects, Neo4j for a knowledge graph
- A BFF gateway, contract-first APIs, CI gates that block architectural violations
- Roughly **25 containers** humming along in Docker Compose

Here's what this post is *not*: a confession that I over-engineered. The architecture was **correct** — derived honestly from the product I was building.

Then I had one more idea. And that idea, without touching a single line of code, invalidated the topology of everything underneath it.

## The platform — and why its architecture was right

The original product was a **multilingual platform for fiction writers**: translation pipelines, a glossary and knowledge graph tracking every character and relationship across a novel, AI-assisted writing with bring-your-own-key. Multi-user, multi-device, delivered over the web.

For *that* product, the derivation was sound:

- Multi-tenant SaaS → services with clear ownership, a database per service
- Heavy async work (translation jobs, entity extraction) → an event spine, outbox, queues
- Many client types (PC, phone, tablet) → a BFF gateway
- Cloud delivery → cloud-native everything

That's the order working as intended: idea → *what* to deliver (a multi-user web platform) → *how* to deliver (cloud SaaS) → architecture. If you're building a multi-tenant SaaS today, most of those boxes are still the right boxes. Given the same inputs, I'd draw them again.

(I can hear the objection already: *"twenty services, for one developer? Even for SaaS, a modular monolith would have been cheaper."* Maybe — that's a legitimate debate. But notice that it's a debate **within** a delivery model: it's about how to slice a cloud system. What happened next happened **across** delivery models — and even the leanest, most disciplined cloud monolith would not have survived it.)

## The feature that was secretly a new product

Over time, the most alive part of the system turned out to be the knowledge graph — the machine-readable model of a book's *world*. Which led somewhere ambitious: a **living world**. Take a novel's universe — its characters, their memories, their motives, its geography and timeline — and make it something a reader can *explore*. Game-like. Shipped on Steam. And in its end state, not *only* a single-player experience, but a **shared living world — an MMO** — where each player's machine runs a piece of the world.

On the roadmap, this looked like scope expansion. A big feature. A new epic.

It was not a feature. It was a **second product wearing my codebase** — and it arrived carrying a different delivery model. The tell wasn't in any diagram. It was in four facts:

**1. The channel.** The living world belongs on **Steam**. You cannot ship a Docker Compose stack to Steam. There is no `docker compose up` on a player's machine. One word — *Steam* — invalidated 25 containers.

**2. The unit economics.** A living world is heavy, *per-user* compute: extraction, embeddings, graph reasoning, continuous LLM calls. On *my* cloud, that cost scales linearly with users — a cost bomb fused to my own growth. On the *user's* machine, their hardware is free and they bring their own AI keys. The economics, not the elegance, decide where compute lives.

**3. The legal posture.** A service that hosts and distributes user content is, to most regulators, a *publisher* — with a publisher's obligations. A tool that processes files on the user's own machine is closer to an *editor* — the Obsidian / VS Code posture. In my market, the distance between those positions is enormous. Architecture doesn't answer this question; it *inherits* the answer.

**4. The constraint that *didn't* matter.** You'd expect "solo developer" to be the binding constraint here — one person, twenty services, who answers the pager at 3 a.m.? That's a pre-AI intuition. I built this platform in three months of AI-assisted development — call it a million lines — and before anyone objects that lines of code are a cost, not an achievement: *exactly*. Code got cheap. What didn't get cheap is everything around the code: the monthly cloud bill, and the path to users. In 2026, a solo project doesn't die of engineering capacity. It dies of operating costs and distribution — and both of those are delivery-model problems, not team-size problems.

And one small discovery that stung most, because it's so concrete: **Neo4j Community Edition is GPLv3.** Perfectly fine inside a cloud service. Fatal inside a closed-source desktop app — you cannot embed it (and shipping a JVM database server next to a Steam game as a "separate process" is its own punishment). That license detail sat invisible in my stack the entire time, and the *delivery question* surfaced it in an afternoon.

The compressed rule I wish I'd had: **a "feature" that changes where your software runs, who pays for its compute, or who bears its legal liability is not a feature. It's a new delivery model asking to be noticed.**

## Architecture is a function — and the input changed

Grady Booch's old definition says architecture is the set of significant design decisions, where significant is *measured by cost of change*. But **which decisions those are depends on how you deliver**. For a SaaS, topology is cheap-ish to evolve and tenant isolation is sacred. For a single-binary node on a player's machine, internal topology is frozen at ship time — and tenancy doesn't disappear, it moves up a level.

So the relationship is:

```
architecture = f(delivery model)      // not f(idea)
```

My original architecture wasn't wrong — `f` was evaluated correctly on the input *"multi-user cloud SaaS."* The living world changed the input to *"a fleet of nodes on player hardware, Steam-delivered, coordinated by a central layer."* Same function, new input, different output: a single-binary local node with embedded storage — and, above it, an HQ to coordinate the fleet.

And here's the part I have to be honest about, because it breaks the tidy version of this story: **the new architecture is not a simplification — it's bigger.** A centralized platform is *one* node. The new model — local-first nodes on many machines, syncing into a multi-level coordination layer — is a distributed system, and distributed systems are strictly harder than centralized ones. I didn't trade a complex architecture for a simpler one. I traded it for a *bigger* one with one decisive property: **it ships in stages.** A node is useful entirely alone — an offline authoring tool, a private world on one machine. Sync makes two devices useful. An HQ makes worlds shareable. The MMO arrives last, assembled from pieces that each earned their keep along the way. The centralized platform had no such ladder — *all* of it had to run before *any* of it was useful.

**The system grew. The shippable unit shrank.** That trade — not "desktop is simpler than cloud" — is what the new delivery model actually bought me.

**The trap, then, isn't designing architecture early.** I did, and it paid for itself for the product it served. The trap is treating the derivation as *finished* — not noticing when an exciting "feature" silently rewrites the delivery model underneath it.

The detection tools are embarrassingly cheap — one-sentence questions:

- Who is this for, and what's the smallest thing that proves the value?
- What channel reaches them?
- Whose machine runs it — and whose money pays for the compute?
- Whose legal problem is the content?
- Who operates it, and can they?

Each is cheap to ask and expensive to skip. The discipline is *re-asking them every time the product grows a major ambition* — because the answer set is what your architecture is actually a function of.

## The asymmetry that saves you

When I finally re-ran the derivation — on paper, before committing to any rewrite — the damage report was instructive: **the losses were not evenly distributed.**

| Transfers to the new delivery model | Written off by it |
|---|---|
| **Domain semantics** — the entity ontology, an eval-validated extraction pipeline with tracked F1 | **Topology** — centralized microservices → local-first nodes + a coordination layer (first shippable unit: one binary) |
| **Contracts** — the transactional-outbox event spine (now getting a second life as the desktop↔cloud sync protocol) | **Storage** — Neo4j + Postgres-per-service → embedded SQLite + in-memory graph |
| **Invariants** — BYOK; "no provider SDK outside one gateway," enforced by a pre-commit gate | **Runtime** — Python services → a Rust core |

Look at the pattern. What survives is **meaning**: what the domain *is*, what the data *means*, which rules must always hold. What gets re-derived is **topology**: how the system is physically arranged, which engines store what, which runtime executes where.

None of this will shock the hexagonal-architecture crowd — ports-and-adapters people have preached "protect the domain" for decades. What a real pivot adds is the **price list**: which investments actually transferred, and which ones a delivery-model change wrote off overnight.

That yields the principle worth keeping — sharper than either "architect everything up front" or "just ship":

> **While your delivery model can still change, the best architecture is the one that assumes the least about it.**

Weight your investment toward delivery-agnostic assets — domain models, contracts, invariants. They transfer across pivots. Defer topology, storage engines, and runtime commitments to the last responsible moment. They don't.

There's research behind the timing instinct, too. A grounded-theory study of 19 production event-sourced systems ([arXiv:2104.01146](https://arxiv.org/abs/2104.01146)) found practitioners explicitly warning against freezing event schemas before the domain stabilizes: *"a high level of maturity of the domain knowledge is a prerequisite."* The same law at three altitudes: event schema, architecture, product. **Don't lock in expensive-to-change decisions while cheap-to-ask questions are still open.**

## What I'm doing now

Two things, deliberately boring:

**Finishing the MVP on the architecture I have.** It is still the correct architecture for the platform product that exists today — it works, it's paid for, and much of it is the seed of the future coordination layer anyway. The rewrite waits.

**Not committing to the rewrite yet.** The living world is real, but its delivery model is still settling. Committing the rebuild *now* would mean evaluating `f` on a speculative input — and a year from now I'd be writing this post again, in mirror image. When the second product proves what it is, its architecture will be derived from facts. Meanwhile, the future core is being designed as the thing that assumes least: a pure domain library — no I/O, no network, no storage opinions — embeddable in a local node *or* wrapped in HQ services. Whatever shape the fleet finally takes, **meaning transfers**.

## The one line

If you take a single sentence from this, take this one:

> **Architecture is a function of your delivery model, not of your idea.**

The corollary is what actually matters day-to-day: when your product grows a new ambition, **re-evaluate the function**. My boxes were never wrong — the inputs changed. Expect that. Build so the expensive parts survive it.

---

*I'm building LoreWeave, a knowledge engine for fiction writers — where one good idea re-priced my entire architecture, and was worth it. If your roadmap ever grew a "feature" that was secretly a second product, I'd genuinely like to hear how you spotted it.*
