# Prior Art: The Engineering Discipline of Event Modelling and Event Storage

**Research brief A2** — for the design round answering (1) *what IS an event?* and (2) *what do we STORE?*
Scope: engineering discipline of event sourcing / event-driven design. **Game-specific event systems are out of scope** (sibling agent).
Date: 2026-08-02. ~30 web sources consulted.

**Reading convention used throughout:**
- **[STATED]** = the cited source says this, in substance, and I have quoted or closely paraphrased it.
- **[INFERRED]** = my synthesis or application to your constraints; the source does not say it.
- **[WEAK]** = the source is a low-authority or anonymised blog; treat as a hypothesis, not evidence.

---

## 0. Executive orientation

The literature converges on a small number of load-bearing rules and disagrees loudly about almost everything else. The convergent core:

1. **An event is a fact that already happened; it cannot be rejected, retried, or refused.** A command is a request that can be refused. This is the *only* distinction the whole field agrees on, and nearly every documented failure mode traces back to violating it.
2. **The event log is the only source of truth; everything else is a fold over it.** Snapshots, projections, read models, caches — derived, disposable, rebuildable.
3. **You can never change a stored event.** You can only add new events, or add new *interpretations* of old ones. Corollary: the event schema is a permanent public contract with your own future self.
4. **Nothing agrees on granularity.** This is the genuinely open design question and the one with the most documented pain in both directions.

The divergent core (where you must make a decision, not look one up):
- Whether the storage-granularity event and the notification-granularity event are the *same object* (CodeOpinion: no; most frameworks: yes by default).
- Whether reaction logic (an event causing an event) belongs in a stateless saga, a stateful process manager, or nowhere.
- Whether to store anything about failure.

---

## A. A PRECISE VOCABULARY — with the test that separates each pair

The word "event" is used for at least **seven** distinct things in this literature. Below, each concept, then the *discriminating test* — a question with a yes/no answer you can apply to a candidate record.

### A1. Command (a.k.a. intent, request)
A request to change state, addressed to exactly one handler, which **may refuse it**.

> "The command represents the intention… It targets a specific audience… the recipient may refuse to do it." — Kurrent/Dudycz, [What's the difference between a command and an event?](https://www.kurrent.io/blog/whats-the-difference-between-a-command-and-an-event/) **[STATED]**

**TEST — Command vs Event: "Can the receiver say no?"**
If yes → command. If the answer is "no, it's already true" → event. This is the *rejectability test* and it is the sharpest line in the field. **[STATED]** — same source; also [Leif Battermann, 12 Things](https://blog.leifbattermann.de/2017/04/21/12-things-you-should-know-about-event-sourcing/) ("events are facts from the past… name them past tense").

**TEST — the naming corollary:** Commands are imperative (`PlaceOrder`, `InitiateShipment`); events are past-participle (`OrderPlaced`, `DepositMade`). A record named in the imperative that lives in the log is a smell. **[STATED]** (Battermann #2; Kurrent).

### A2. Fact / Event (the stored, sourced kind)
An immutable record of a state transition that **has already been decided and accepted**. Its purpose is *reconstruction*: `f(state, event) -> state` must be a pure function. **[STATED]** — Battermann #8, #9.

**TEST — Fact vs Command, the second edge (the decisive one for an event-sourced engine):**
The *eulerfx* formulation is the most precise thing I found on this question:

> "a program can control its output, but not its input" — [Command Sourcing vs Event Sourcing](https://gist.github.com/eulerfx/11227933) **[STATED]**

Event sourcing stores **outputs**; command sourcing stores **inputs**. Storing commands means storing something whose *interpretation depends on context you do not control* — so:

> "you can't simply replay a stream of logged commands at some arbitrary time and hope to get the same outputs" **[STATED]**

**⇒ TEST: "If I replay this record ten years from now against different code, must it produce the same state transition?"**
If yes → it is an event. If the answer depends on re-running a decision → it is a command, and storing it in the event log makes your log non-deterministic. **[INFERRED, but directly implied by eulerfx]**

### A3. Domain event (DDD sense — a notification inside a boundary)
"Something that happens in the domain that is important to domain experts" (Fowler, [Domain Event](https://martinfowler.com/eaaDev/DomainEvent.html)). Note this is a *modelling* concept, not a *storage* concept.

**TEST — sourced event vs domain event: the GRANULARITY test.**
CodeOpinion states these are genuinely different objects, distinguished by granularity:

> Events persisted to an event store are "about state… capturing events to represent the transitions in state," while domain events function as "notifications/integrations within or outside a service boundary." Fine-grained `ItemAddedToCart` / `ShippingInformationDefined` capture state transitions, but only `OrderPlaced` — "the completion of our workflow" — is suitable as a domain/integration event. "Not all events in event sourcing are domain events."
> — [Domain Events in Event Sourcing? Not Exactly!](https://codeopinion.com/domain-events-in-event-sourcing-not-exactly/) **[STATED]**

**⇒ TEST: "Would a component outside this aggregate's boundary make a decision on this record?"**
If no → it is a *storage* event only (private). If yes → it is additionally a domain/integration event and now carries a compatibility obligation.

### A4. Integration event (an outside event, a published contract)
An event deliberately published across a service/bounded-context boundary.

**TEST — inside vs outside:** Comartin's framing:
> "Inside events are private within a service boundary… you have more flexibility for evolving and changing," whereas outside events require versioning strategies like APIs.
> — [Beware! Anti-patterns in Event-Driven Architecture](https://codeopinion.com/beware-anti-patterns-in-event-driven-architecture/) **[STATED]**

The strongest version of this warning:
> "If you use Event Sourcing at global scale, you expose your persistence layer. Your persistence becomes your public API… Event Sourcing is a local decision made by a single Bounded Context!"
> — [Why Event Sourcing is a microservice anti-pattern](https://dev.to/olibutzki/why-event-sourcing-is-a-microservice-anti-pattern-3mcj) **[STATED]**

**⇒ TEST: "Does a consumer I do not deploy read this?"** If yes, it is a published contract, and its schema is frozen at a different (much slower) cadence than an internal event.

### A5. Event-carried state transfer (ECST) message
An event whose payload is deliberately fattened so the receiver never has to call back.
> "the consumer system keeps a copy of all the data that it will ever need, and the event source system has to broadcast in its event all the data that the downstream systems will need."
> — Fowler, [What do you mean by "Event-Driven"?](https://martinfowler.com/articles/201701-event-driven.html) **[STATED]**

**TEST — ECST vs notification: "Is the payload sized for the *producer's* state transition, or for the *consumer's* query needs?"**
If the latter, it is ECST and it is now a data-distribution contract, which Comartin warns is where CRUD-shaped events creep in. **[STATED/INFERRED mix]**

### A6. Projection trigger / read-model input
The *same* event, consumed by a projector. It is not a distinct record — it is a distinct **role**. Dudycz's Emmett taxonomy separates the roles cleanly:

> **Consumer** = transport (poll/subscribe, forward). **Processor** = "processing logic… checkpointing: tracking which messages have been processed." **Projector** = a processor that "transforms events into queryable state." **Reactor** = a processor that "triggers side effects after a business fact has happened."
> — [Consumers, projectors, reactors and all that messaging jazz](https://www.architecture-weekly.com/p/consumers-projectors-reactors-and) **[STATED]**

**TEST — projector vs reactor: "If I replay this handler from position 0 tomorrow, is the outside world affected?"**
No → projector. Yes → reactor. This is the single most operationally consequential distinction in the taxonomy. **[INFERRED from the Emmett definitions + Fowler's replay-mode gateway]**

### A7. Notification (user-facing / ephemeral signal)
An email, a push, a toast, a "your turn" ping. This is a *reactor output*, not an event.

**TEST — notification vs event: "Is this a record of what happened, or a record that someone was told what happened?"**
Being told is itself potentially a fact worth recording (`PlayerNotified`), but the *notification itself* — the message, the delivery — is not a state transition of the aggregate. **[INFERRED; grounded in Fowler's gateway discussion where external calls are explicitly excluded from replay.]**

### A8 (bonus). The two things everyone accidentally builds
- **CRUD event / property-sourced event** — `CustomerNameChanged`, `EntityUpdated`. See §D/§E.
- **Passive-aggressive event** — an event that is really a command. Fowler names this exactly:
  > "A simple example of this trap is when an event is used as a passive-aggressive command. This happens when the source system expects the recipient to carry out an action, and ought to use a command message to show that intention, but styles the message as an event instead."
  > — [Fowler, 201701-event-driven](https://martinfowler.com/articles/201701-event-driven.html) **[STATED]**
  Dudycz's expansion: it "creates hidden sequential dependencies disguised as loose coupling," obscures the critical path, and produces an "I-already-did-my-job" mentality with unhandled failures. Fix: an explicit coordinator that sends **commands** for critical-path work and publishes **events** only for autonomous subscribers. — [Passive-Aggressive Events](https://event-driven.io/en/passive_aggressive_events/) **[STATED]**

### Summary table of the discriminating tests

| Pair | The test (one question) |
|---|---|
| Command vs Event | *Can the receiver say no?* |
| Command vs Event (replay edge) | *Replayed in 10 years against new code, does it produce the same transition?* |
| Sourced event vs Domain event | *Does anyone outside the aggregate boundary decide on it?* |
| Domain event vs Integration event | *Does a consumer I don't deploy read it?* |
| Notification vs ECST | *Is the payload sized for my transition or their query?* |
| Projector vs Reactor | *Does replaying this handler from 0 touch the outside world?* |
| Event vs Notification | *Is it what happened, or that someone was told?* |
| Event vs CRUD-diff | *Does the name state a business outcome, or a field that moved?* |

---

## B. THE STORAGE DECISION TABLE

| # | Concept | Verdict | Reason (with source) |
|---|---|---|---|
| 1 | **Command / intent** | **TRANSIENT** (accept: log for ops, outside the fold) | Replaying commands is non-deterministic — "a program can control its output, but not its input" ([eulerfx](https://gist.github.com/eulerfx/11227933)). Storing them *in the same log* as facts makes the fold depend on re-deciding. **[STATED + INFERRED]** |
| 2 | **Rejected / failed command** | **NOT IN THE LOG** | The strongest documented decision I found is UK GOV Publishing API [ADR-002 "Don't log events which result in error"](https://docs.publishing.service.gov.uk/repos/publishing-api/arch/adr-002-dont-log-events-which-result-in-error.html): logging them puts "information that has no bearing on the behaviour of the system" in the log, and "an attempt to replay an event history containing rejected events would encounter errors." Consequence they accepted: validation must be **synchronous** in the request/response cycle. **[STATED]** |
| 2b | **Rejection as a *domain fact*** | **DURABLE — but only if it's a real business outcome** | If a saga must compensate on rejection, the rejection is a fact with consequences and gets its own event (`PaymentDeclined`, not `PayCommandFailed`). Practitioner debate documented at [I don't byte — Commands can be rejected](https://idontbyte.jaun.org/blog/2020/02/eventsourcing-notes-on-commands) and [Jonathan Oliver, Sagas, Event Sourcing, and Failed Commands](https://blog.jonathanoliver.com/sagas-event-sourcing-and-failed-commands/). **[STATED that the debate exists; the resolution rule is INFERRED]** |
| 3 | **Fact / sourced event** | **DURABLE, append-only, forever** | The SSOT. Immutable: "The moment you allow a single edit, everything becomes suspect" ([Young notes](https://github.com/luque/Notes--Versioning-Event-Sourced-System)). **[STATED]** |
| 4 | **Event metadata: `message_id`, `correlation_id`, `causation_id`, stream version, timestamp** | **DURABLE, alongside the event** | Battermann #5: minimal structure is `StreamId` + `Data` + `Version`; optional metadata = type, correlation id, timestamp, actor. Young's three-id rule (§C). **[STATED]** |
| 5 | **Decision inputs that came from outside** (exchange rate, dice roll, wall-clock, an LLM response, another aggregate's state at decision time) | **DURABLE — must be captured INTO the event payload** | Fowler is explicit: "If I ask for an exchange rate on December 5th and replay that event on December 20th, I will need the exchange rate on Dec 5 not the later one." Remedy: gateways "remember the responses to its queries and use them during replay." ([Fowler, Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html)) **[STATED]** — see §F1. |
| 6 | **Derived aggregate state** | **DERIVED — NEVER STORED as truth** | `f(state,event)->state`. **[STATED]** Battermann #3, #8. |
| 7 | **Snapshot** | **DERIVED — storable as a CACHE, never as a source** | "Snapshots are not a replacement for the event stream — they are a cache; events remain the source of truth, and snapshots can always be rebuilt if lost." (Kurrent/practitioner corpus, [Snapshots in Event Sourcing](https://www.kurrent.io/blog/snapshots-in-event-sourcing/)). **[STATED]** Matches your existing constraint exactly. |
| 8 | **Projection / read model** | **DERIVED — storable, disposable, rebuildable** | "The same logic will generate the same result for the same events," enabling complete rebuilds. ([Projections and Read Models guide](https://event-driven.io/en/projections_and_read_models_in_event_driven_architecture/)) **[STATED]** |
| 9 | **Projection checkpoint / processor position** | **DURABLE — but as *operational* state, not in the event log** | Processors own "checkpointing: tracking which messages have been processed" ([Emmett taxonomy](https://www.architecture-weekly.com/p/consumers-projectors-reactors-and)). It is not a domain fact; it is a cursor. **[STATED for the mechanism, INFERRED for the placement rule]** |
| 10 | **Process-manager / saga state** | **DURABLE — and ideally itself event-sourced in its own stream** | A process manager "can be modelled as a state machine and makes decisions based not only on incoming events but also the current state of the process" ([Saga and Process Manager](https://event-driven.io/en/saga_process_manager_distributed_transactions/)). It has state ⇒ that state needs a home. **[STATED for statefulness; the "own stream" recommendation is INFERRED]** |
| 11 | **Notification / email / push / toast** | **TRANSIENT — reactor output, must never be in the fold** | The whole point of the projector/reactor split; Fowler's gateway "replay mode" exists because "external systems don't know the difference between real processing and replays." **[STATED]** |
| 12 | **Integration/published event** | **DERIVED FROM the log, published via an OUTBOX — do not let consumers read your store** | "just because you have an event store, does not mean another service can reach out to your event store" ([CodeOpinion](https://codeopinion.com/domain-events-in-event-sourcing-not-exactly/)). Outbox: record the outbound message in the same transaction as the state change ([microservices.io transactional outbox](https://microservices.io/patterns/data/transactional-outbox.html)). **[STATED]** |
| 13 | **Idempotency / dedup record (inbox)** | **DURABLE, bounded TTL, outside the log** | "store the processed message ids and put a unique constraint on them — if you perform the database change in the same transaction as storing message id, then your database will make sure that your operation is idempotent" ([Outbox/Inbox and delivery guarantees](https://event-driven.io/en/outbox_inbox_patterns_and_delivery_guarantees_explained/)). Stripe's documented window is 24h ([Stripe: Designing robust and predictable APIs with idempotency](https://stripe.com/blog/idempotency)); PayPal 45 days. **[STATED]** |
| 14 | **Field-level diffs / `EntityUpdated` / `XChanged`** | **NEVER — anti-pattern** | "Publishing events like *LastNameChanged* is called *Property Sourcing*… We'll get many tiny, copy/pasted, meaningless events." ([Property Sourcing](https://event-driven.io/en/property-sourcing/)) And: "CRUD-driven events are not explicit" — they say *that* data changed, not *why* ([Comartin](https://codeopinion.com/beware-anti-patterns-in-event-driven-architecture/)). **[STATED]** |
| 15 | **Row-level DB changes (CDC)** | **NEVER, as domain events** | "CDC is not the same as event sourcing, and raw row changes are not always good domain events." "Copying raw tables between services can create hidden coupling." (Debezium ecosystem corpus; [Debezium: ES vs CDC](https://debezium.io/blog/2020/02/10/event-sourcing-vs-cdc/) — page 403'd on direct fetch, content via search index). **[STATED, via search-index quotation — direct fetch blocked]** |
| 16 | **Anything computable from earlier events + pinned rules** | **DERIVED — never stored** *…except when the computation itself is non-reproducible (row 5)* | This is the real tension and it is where teams get it wrong in **both** directions. See §F1. **[INFERRED]** |

---

## C. THE REACTION-CHAIN PROBLEM — "an event causes an event"

This is the part of your brief with the most divergence in the literature. Here is every documented approach, with cascade-bounding and replay behaviour.

### C0. The failure mode, named
Practitioner war-story corpus reports the canonical shape: a `UserUpdated` event triggered `ProfileUpdated`, which triggered another `UserUpdated`, "ad infinitum. The system processed 500K events/hour until OOM killed it." Fix reported: causation IDs to track chains + idempotency keys. ([When Event Sourcing Fails: War Stories from Production](https://dev.to/alex_aslam/when-event-sourcing-fails-war-stories-from-production-1nk2)) **[WEAK — anonymised, no company/date; treat as an illustrative shape, not evidence]**

The structural version of the same warning, from a higher-authority source:
> "The danger is that it's very easy to make nicely decoupled systems with event notification, without realizing that you're losing sight of that larger-scale flow." — [Fowler](https://martinfowler.com/articles/201701-event-driven.html) **[STATED]**

And Comartin: chains of handlers that republish create "a hidden distributed transaction" — if one step fails, the earlier ones already committed. **[STATED]**

### C1. Approach: **Projection emits an event** (reactive projection)
**Verdict: documented as forbidden.**
> Projections must never: "❌ Emit new events ❌ Call external systems ❌ Trigger domain logic ❌ Modify other projections. Violations create temporal dependencies and coupling."
> — [Projections and Read Models guide](https://event-driven.io/en/projections_and_read_models_in_event_driven_architecture/) **[STATED]**

- **Cascade bounding:** none. A projection is rebuilt from position 0 routinely; emitting from it multiplies the log on every rebuild.
- **Under replay:** catastrophic — rebuild becomes write-amplifying and non-idempotent.

### C2. Approach: **Reactor** (a processor whose job is side effects)
- **Shape:** subscribes with its own checkpoint; performs external effects; may issue **commands** (not events).
- **Cascade bounding:** by checkpoint. A reactor never re-fires history, because its checkpoint is already past it. Spatie's framework documents this as a hard rule: "Reactors handle side effects… only intended to work when events are originally fired, not when replaying events. Reactors will never get called when replaying events." ([Spatie laravel-event-sourcing, Replaying events](https://spatie.be/docs/laravel-event-sourcing/v7/advanced-usage/replaying-events)) **[STATED]**
- **Under replay:** **must be excluded from replay** — this is exactly Fowler's gateway rule: "The gateway should handle that distinction by having a reference to the event processor and checking whether it's in replay mode before passing the external call off." ([Fowler](https://martinfowler.com/eaaDev/EventSourcing.html)) **[STATED]**
- **Trade-off named:** you gain replay safety, and you pay by making the reaction *not* part of the fold — so a rebuild will not re-derive "the mail was sent." If you need that fact, the reactor must emit a **fact event** (`MailSent`) which *is* in the fold, and its own re-firing must be guarded by the checkpoint, not by the fold.

### C3. Approach: **Stateless Saga** (event in → command out)
> "waits for the event. When a success event arrives, dispatches a command based on the event data." No internal state; decisions from incoming event data only.
> — [Saga and Process Manager](https://event-driven.io/en/saga_process_manager_distributed_transactions/) **[STATED]**

- **Cascade bounding:** by *type*. Each `Handle(EventType) -> SendCommand()` mapping is a static edge; the graph is inspectable at compile time. Cycles are visible in the code.
- **Under replay:** safe *iff* it is checkpointed like a reactor. Its output is a **command**, which goes through the normal decide-path — so the command can be *rejected*, which is a natural cascade brake.
- **Trade-off named:** cheap and inspectable, but it cannot express "wait for both A and B", "time out after 3 turns", or "only if not already compensated."

### C4. Approach: **Stateful Process Manager** (state machine)
> "responsible for managing stateful, long-running processes… makes decisions based not only on incoming events but also the current state of the process." Long-running "refers to the plurality of events that make up the process and not the passage of time."
> — [O'Reilly, Real-World Event Sourcing ch.4](https://www.oreilly.com/library/view/real-world-event-sourcing/9798888651612/f_0034.xhtml) / [Dudycz](https://event-driven.io/en/saga_process_manager_distributed_transactions/) **[STATED]**

**Why is a process manager stateful and a projection not?** — the direct answer to your question:
A projection's output is a *pure function of the events so far*: `fold(events) -> view`, and the view is **discardable** because it can always be recomputed. A process manager's output is a *decision to act*, and acting is not recomputable — once a command has been sent, "have I already sent it?" is a fact that cannot be re-derived from the aggregate's events alone. It therefore needs its own durable state (its position in the state machine) and, ideally, its own event stream. **[INFERRED — this synthesis is mine; the components (statefulness, checkpointing, non-idempotence of effects) are each STATED across the Emmett taxonomy, Dudycz, and Fowler]**

- **Cascade bounding:** by **state machine reachability** — the strongest bound available. A cycle is a modelling error you can detect statically; a "already-completed" state absorbs late/duplicate events.
- **Under replay:** the PM's own stream replays deterministically (it's event-sourced); but its *commands* must be suppressed in replay mode, same as a reactor.
- **Trade-off named:** the strongest bound and the highest cost. Dudycz: "unless I have a really complex workflow, I'd try to avoid using a Process Manager." **[STATED]**

### C5. Approach: **Choreography vs Orchestration** (the meta-choice)
- **Choreography:** services react to each other's events; no coordinator. *Advantage:* no single point of failure, independence. *Disadvantage:* "fragmented process visibility; difficult to grasp overall workflow." **[STATED, Dudycz]**
- **Orchestration:** one component conducts. *Advantage:* "precise responsibility boundaries; clear process visibility." *Disadvantage:* "introduces coupling." **[STATED, Dudycz]**
- **Cascade bounding:** orchestration bounds cascades *by construction* (the coordinator is the only edge-adder); choreography does not bound them at all — the 500K-events/hour loop in C0 is a choreography failure. **[INFERRED]**

### C6. Approach: **Event Modeling's "Automation / TODO-list" pattern**
Dymitruk's method models reaction explicitly as a **pattern with a read model in the middle**:
> **Automation**: `Event(s) -> View -> Automated Trigger -> Command -> Event(s)` — "enables system-driven actions using the same information flow as user interactions."
> — [Event Modeling cheatsheet](https://eventmodeling.org/posts/event-modeling-cheatsheet/) **[STATED]**

This is, in my reading, the cleanest architectural answer available: **an event never directly causes an event.** It causes a *view* (a "todo list" of outstanding work), and a processor reads that view and issues a **command**, which the decider may accept or reject, producing an event.
- **Cascade bounding:** total — the only thing that can create an event is a command accepted by a decider. There is no event→event edge in the model at all.
- **Under replay:** the view rebuilds deterministically; the automation processor is checkpointed and suppressed during rebuild.
- **Trade-off named:** an extra hop and an extra derived artifact per automation; you pay in structure to buy an acyclic causal graph. **[INFERRED for the bounding/replay claims; the pattern itself is STATED]**

### C7. The ID discipline that makes any of the above debuggable
Greg Young's three-id rule:
> "Every message has 3 ids: MessageId, CorrelationId, CausationId. If you are responding to a message, you copy its correlation id as your correlation id, and its message id is your causation id. This allows you to see an entire conversation (correlation id) or to see what causes what (causation id)."
> — via [Arkency](https://blog.arkency.com/correlation-id-and-causation-id-in-evented-systems/) and [Rails Event Store docs](https://railseventstore.org/docs/core-concepts/correlation-causation) **[STATED]**

- **`correlation_id` answers:** *"What all happened because of this original trigger?"* (the whole conversation, transitively).
- **`causation_id` answers:** *"What directly caused THIS?"* (one edge of the graph; follow it repeatedly to get the exact chain).
- **With only `correlation_id`:** you get the set of everything in the conversation but **not its shape** — you cannot tell a 3-deep chain from 3 parallel siblings, which is precisely what you need to diagnose a runaway cascade. **[INFERRED — Arkency asserts the loss but I could not find Young stating it in these words]**
- **With only `causation_id`:** you can walk the chain upward but cannot cheaply ask "show me everything from turn 47." **[INFERRED]**
- Rails Event Store materialises both as streams: `correlation-{id}` and `causation-{id}`. **[STATED]**

**Cascade bounding via IDs:** a depth counter or a cycle check on the causation chain is the cheapest runtime brake; this is what the war-story team reported adding. **[WEAK]**

### C8. Causal ordering: do you need Lamport / vector clocks?
- Lamport clocks give a **total order** but "do not capture information about non-causality (concurrency)." Vector clocks detect concurrency/conflict. ([Aeron, Logical Clocks](https://aeron.io/docs/distributed-systems-basics/logical-clocks/); practitioner summaries) **[STATED]**
- Key practical framing found: *"if you use Kafka, offset ordering within a partition is your Lamport clock, and you should not compare offsets across partitions."* **[STATED, from search-index synthesis]**
- **Application to your constraints [INFERRED]:** with **single-writer-per-aggregate-stream**, the per-stream version number *is* your Lamport clock and it is sufficient *within* a stream. Vector clocks buy you conflict *detection*, which you have designed away (single writer). What you may still need is a **cross-stream causal order** for replay of multi-aggregate interactions — and `causation_id` gives you that as a DAG without needing clocks at all, provided you also have a global append sequence to break ties deterministically. A global monotonic position + causation edges is strictly cheaper than vector clocks and sufficient for reconstructability (as opposed to conflict resolution).
- Out-of-order delivery is a documented real failure: receiving "Offer Accepted" after "Acceptance Withdrawn" produces the wrong state, and **retries themselves cause reordering** ([Lessons from developing and supporting event sourcing based system](https://codesimple.blog/2019/12/14/event-sourcing-lessons/)). **[STATED]**

---

## D. THE VERSIONING TRAP — documented cases where a stored event became misinterpretable

### D1. The canonical rule
> "A new version of an event must be convertible from the old version of the event. If not, it is not a new version of the event but rather a **new event**." — Greg Young, via secondary summaries of [Versioning in an Event Sourced System](https://leanpub.com/esversioning) **[STATED, via secondary source — I could not fetch the book body; Leanpub served only the ToC]**

This is the whole trap in one line: **if the meaning changed, it is not a version bump, it is a different event type.**

### D2. Case: the semantic change that upcasting *cannot* fix
> "Sometimes the change is not just structural. The business meaning of the event has changed. When that happens, create a different event entirely… **An upcaster can't fix a semantic change because the old data doesn't carry enough information to derive the new meaning.**"
> — Event-sourcing playbook corpus, surfaced via search ([Event Sourcing Without Regret](https://medium.com/@Modexa/event-sourcing-without-regret-a-java-playbook-acc11f2b398c)) **[STATED]**

This is exactly your "payload upcasts cleanly but MEANING changed" failure. The defence is **type identity**, not schema migration.

### D3. Case: business *logic* evolved while the event schema did not
The SSENSE-TECH series documents the shape (article body paywalled; the framing surfaced in the search index and is corroborated by Fowler): a domain computes a charge from *a base amount + an exchange rate*. If only the base amount is stored and the rate is looked up at fold time, replay after the rate changes produces **a different charge for the same history**. Fowler states the general form directly ("I will need the exchange rate on Dec 5 not the later one"). ([Fowler](https://martinfowler.com/eaaDev/EventSourcing.html); [SSENSE-TECH Part IV](https://medium.com/ssense-tech/event-sourcing-part-iv-evolving-your-system-de3d41c31053) — **paywalled, framing only**) **[STATED (Fowler) / PARTIAL (SSENSE)]**

**Defence:** capture the *decision inputs and the decision output* in the event. The event must be self-sufficient for the fold.

### D4. Case: new field + old events + new logic = retroactive money
> "A team added a `discount_code` field to `OrderPlaced` events. Old projections ignored it — until a replay applied **2024 logic to 2022 data**, giving customers unintended discounts." Fix: upcasters + tagging projections with schema-compatibility versions.
> — [War Stories from Production](https://dev.to/alex_aslam/when-event-sourcing-fails-war-stories-from-production-1nk2) **[WEAK — anonymised, no verifiable company/date. The *shape* is corroborated by D2/D3; the incident itself is not independently verifiable.]**

This is the sharpest illustration of the trap for your engine: **an event that folded correctly under ruleset v1 folds *differently* under ruleset v2, silently, with no schema error.** Your pinned-ruleset-digest SSOT is precisely the defence — see §F2.

### D5. Case: the ordinal/tag reassignment — the mechanised defence exists
Protobuf documents the exact mechanism your brief asks about:
> "The same field number must not be used again in your updated message type… make the field number **reserved**, so that future users of your .proto can't accidentally reuse the number." And for enums: "No enum value is deleted without reserving the number. Though deleting an enum value isn't directly a wire-breaking change, **reusing these numbers in the future is likely to result in bugs**."
> — [Protobuf Proto Best Practices](https://protobuf.dev/best-practices/dos-donts/), [Enum Behavior](https://protobuf.dev/programming-guides/enum/) **[STATED]**

Why it corrupts: "every protobuf field is encoded as a key-value pair on the wire. The key combines the field number and the wire type into a single varint" — so old bytes silently decode under the new meaning. **[STATED]**

**Defence, mechanised:** `reserved` numbers/names, enforced by a schema linter ([Buf breaking-change rules](https://docs.buf.build/breaking/rules)). **[STATED]**
**[INFERRED for you]:** the same discipline generalises to JSON: never reuse a *string enum value* or a *field name* for a different meaning; retire it into a reserved list checked by a lint. A JSON weak-schema event store has **no** wire-level protection at all — it will happily map `"kind": "fire"` onto a `fire` that now means something else.

### D6. The weak-schema trade — what it buys and what it forbids
Young's recommended default is weak schema (JSON/XML + mapping rather than deserialisation):
> Field in both → use the JSON value; field in JSON only → ignore it; field in instance only → apply a default.
> — [Notes on Versioning in an Event Sourced System](https://github.com/luque/Notes--Versioning-Event-Sourced-System) **[STATED]**

But it comes with two hard constraints from the same source:
1. **No renaming allowed** — renaming breaks backward compatibility. **[STATED]**
2. **Programmatic validation required** — you must verify expected fields exist after mapping, because weak schema will *silently* hand you a default. **[STATED]**

Constraint 2 is the one that bites: weak schema converts a loud deserialisation failure into a **quiet wrong value**. **[INFERRED]**

### D7. What Marten (a production event store) documents as the never-rule
> "Never modify stored events… **The best strategy is not to change the past data but compensate our mishaps.**" Upcasting runs "each time the event is deserialized," so upcasters that call out to anything risk N+1.
> — [Marten: Events Versioning](https://martendb.io/events/versioning) **[STATED]**

### D8. Dudycz's meta-defence: don't have long-lived schemas
> "The best strategy is avoiding versioning entirely through careful upfront design and **keeping streams short-lived**." Also: "we have to support the structure of the old event for as long as that stream's events live in our store."
> — [Simple events versioning patterns](https://event-driven.io/en/simple_events_versioning_patterns/), [Keep your streams short](https://www.kurrent.io/blog/keep-your-streams-short-temporal-modelling-for-fast-reads-and-optimal-data-retention) **[STATED]**

**⇒ Schema lifetime is a function of stream lifetime.** A stream that lives forever gives you a schema you must support forever.

### D9. Retention / compaction — the preconditions, documented
From the "closing the books" pattern ([Kurrent](https://www.kurrent.io/blog/keep-your-streams-short-temporal-modelling-for-fast-reads-and-optimal-data-retention)) plus EventStoreDB operational docs ([Kurrent scavenging](https://docs.kurrent.io/server/v24.10/operations/scavenge), [stream metadata](https://docs.kurrent.io/server/v22.10/streams)):

Before you may drop old events: **[STATED]**
1. The business period must be **closed and summarised** (a closing event carries forward the balance).
2. Events must be **copied to cold storage** first — "Archiving differs from removal."
3. **Read models must be prepared** — a summary/carry-forward event must capture what a future rebuild needs.
4. **Ordering metadata preserved** — original positions recorded so a rebuild can restore order.

Operational traps, documented: **[STATED]**
- "Scavenging is **destructive**. Once a scavenge has run, you cannot recover any deleted events except from a backup."
- `$maxAge`/`$maxCount` mark events eligible for removal but they are "still readable" via `$all` until scavenged — so a projection can appear healthy and then silently lose its source.
- **⇒ your snapshot-before-truncate precondition is not "take a snapshot"; it is "emit a carry-forward FACT event that makes the truncated prefix unnecessary."** A snapshot is derived and therefore cannot license deletion of the thing it was derived from. **[INFERRED — this is the sharpest consequence of your own "snapshots are never a source" constraint]**

### D10. GDPR / erasure — the escape hatch and its cost
Crypto-shredding: encrypt per-subject payloads, delete the key to make the data unreadable. Cost: "key management and encrypted payloads that plain CRUD storage never needs," and it does not remove the need for retention policies. ([Event-Driven.io GDPR](https://event-driven.io/en/gdpr_in_event_driven_architecture/), [patchlevel](https://patchlevel.de/blog/mastering-sensitive-data-handling-and-gdpr-compliant-secure-data-removal-with-event-sourcing)) **[STATED]**
**[INFERRED]** — a shredded event is an event whose *fold contribution is now undefined*. If PII participates in the fold, shredding breaks reconstructability; so PII must be kept **out of the fold** (referenced, not folded).

---

## E. WHAT THE CRITICS SAY — the strongest arguments against, and what those teams did instead

### E1. Chris Kiehl — "Don't Let the Internet Dupe You, Event Sourcing is Hard"
[chriskiehl.com/article/event-sourcing-is-hard](https://chriskiehl.com/article/event-sourcing-is-hard) **[STATED]**

The strongest single critique I found. Its arguments, in order of force:
1. **The audit-log promise is void the moment you need to evolve.** "Once you hit this point, you've got a decision to make: what to do with the irrelevant / wrong / outdated events." Any rewriting destroys the historical accuracy that was the selling point.
2. **Raw event streams destroy boundaries.** "the raw event stream subscription setup kills the ability to locally reason about the boundaries of a service."
3. **Chattiness.** "most of it ends up being pure noise that actually needs filtered out, both by end users, and by consuming sub-systems."
4. **Materialisation lag has user-visible teeth.** "Newly created data will 404, deleted items will awkwardly stick around, duplicate items will be returned."
5. **Projection multiplication.** One extra projection "doubles the amount of code that touches your event stream."

**What he recommends instead:**
- Answer first: **"For which core problem is event sourcing the solution?"** — "auditability" and "flexibility" are not answers.
- **A plain history table** "gets you 80% of the value of a ledger with essentially none of the cost."
- **CQRS without ES**: "You can have all the power of different projections without putting the ledger at the heart of your system."
- If you only need async decoupling, "Put a queue between those two."

### E2. Udi Dahan — most people shouldn't have
Dahan's position, as recorded in secondary sources: most people using CQRS *and* event sourcing shouldn't have; both suit "relatively complex domains" and cause "more headaches and unnecessary complexity" in CRUD-y ones; **"event sourcing should not be your top-level architecture"** though the system should be event-*driven*. CQRS suits *collaborative* domains (multiple users on the same data), not single-user-per-datum domains. ([Clarified CQRS](https://udidahan.com/2009/12/09/clarified-cqrs/); secondary summaries) **[STATED via secondary; the "Clarified CQRS" primary is consistent]**

His constructive contribution to *your* question is the other article:
> **"Don't Delete — Just Don't."** Delete is not a business operation; it is a technical action masquerading as one. "We've been exposing users to entity-based interfaces with 'create, read, update, delete' semantics… even though it's an extremely poor fit." Products are *discontinued*; orders are *cancelled*; employees are *terminated*. **Ask users why they're deleting before coding any solution.**
> — [udidahan.com/2009/09/01/dont-delete-just-dont](https://udidahan.com/2009/09/01/dont-delete-just-dont/) **[STATED]**

This is the constructive half of the CRUD-event critique: the anti-pattern is not "deleting", it's **failing to name the domain concept**.

### E3. Oliver Libutzki — ES events are a *local* decision, not a public API
> "If you use Event Sourcing at global scale, you expose your persistence layer. Your persistence becomes your public API." Instead: publish deliberately-designed **Domain Events** (Open Host Service + Published Language, or Customer/Supplier), keeping internal ES events private.
> — [dev.to/olibutzki](https://dev.to/olibutzki/why-event-sourcing-is-a-microservice-anti-pattern-3mcj) **[STATED]**
Notable counterargument from the comments: the critique lands on *property-sourced* events, not on genuine domain concepts. **[STATED]**

### E4. The Debezium team — prefer outbox+CDC first
> "CDC with the Outbox pattern is usually a better alternative to full Event Sourcing and is compatible with CQRS. Event Sourcing still has value in some use cases, but they encourage trying the Outbox approach first."
> — [debezium.io/blog/2020/02/10/event-sourcing-vs-cdc](https://debezium.io/blog/2020/02/10/event-sourcing-vs-cdc/) **[STATED via search index — direct fetch returned HTTP 403. Quote is from the search engine's extract of that page; I could not verify it against the page body myself.]**

### E5. Hacker News practitioner thread on "Event Sourcing is Hard"
[news.ycombinator.com/item?id=19072850](https://news.ycombinator.com/item?id=19072850) **[STATED that these claims appear in the thread; the claims themselves are unverifiable practitioner reports — treat as anecdote]**
- **Space/replay:** "Events are pretty much a database commit log. This is extremely space inefficient to keep around." One team's CI eventually needed *days* to rerun events.
- **Versioning across consumers:** "you probably need to update the projection in 5-10 different projects" simultaneously; consensus in-thread that **no good versioning solution exists**.
- **The $50–100M cautionary tale:** a Gulf-State programme mandated ES+CQRS+DDD across all services and collapsed after ~18 months. Root cause reported: "The async-everywhere nature of CQRS/ES is super complex where coordination is required" — and, damningly, shared command/event definitions produced "the most coupled system" despite loose-coupling goals.
- **Where it *did* work:** finance/trading with LMAX-style single-threaded processors, strict ordering, small purposeful streams, "millions of messages per second" replay. Cost: "You need more senior devs than your average CRUD system."
- **What they did instead:** traditional DB + selective event logging for critical flows; CQRS without ES; append-only audit log alongside a mutable state store.

### E6. The dissenting voice on granularity (a genuine disagreement to be aware of)
Against the property-sourcing consensus, one production write-up explicitly **advocates fine-grained delta events**:
> "Generic event bodies gradually start picking information that is either redundant or conflicting in some scenarios" — making validation and routing easier with fine-grained, delta-based events.
> — [Lessons from developing and supporting event sourcing based system](https://codesimple.blog/2019/12/14/event-sourcing-lessons/) **[STATED]**

This is a real, documented tension with Dudycz's property-sourcing rule. My reading of the reconciliation: Dudycz is arguing about the *name and business meaning* (a `LastNameChanged` event names a column); codesimple is arguing about the *payload* (a fat generic payload accumulates contradictions). **Both are compatible with: narrow business-meaningful name + payload containing exactly the decision's outputs.** **[INFERRED]**

### E7. The granularity failure modes, stated in both directions
From [Barry O'Sullivan](https://barryosull.com/blog/event-granularity-modelling-events-in-event-driven-applications/) and [thisprogrammingthing](https://www.thisprogrammingthing.com/2020/what-is-the-correct-granularity-for-our-events/): **[STATED]**
- **Too coarse:** `AccountStatusChanged` — "None of our processes care if the status changed generically, they care if it changed to a specific value." Listeners must inspect the payload and re-derive intent ⇒ domain logic leaks into every subscriber.
- **Too fine:** `CustomerFirstnameChanged` + `CustomerLastnameChanged` — "No service cares if they happen independently… they just care about the value as it is now." Subscribers must correlate multiple events before they can act ⇒ every subscriber grows a mini state machine.
- **The hybrid disaster:** generic *name* plus excessive *data* — suffers both.
- **Documented root causes:** deriving events from **UI mockups** rather than from domain expertise; and over-correcting from coarse to fine **by guesswork** instead of by asking a domain expert.
- **Recommended remedy:** event storming with a domain expert; test the design against real internal subscribers before exposing anything.

---

## F. THE 3–5 FINDINGS MOST SHARPLY APPLICABLE TO "WHAT IS AN EVENT / WHAT DO WE STORE"

### F1. The fold must be closed: an event must carry every input the decision consumed that the log cannot re-derive
Fowler states it as an external-query problem — "If I ask for an exchange rate on December 5th and replay that event on December 20th, I will need the exchange rate on Dec 5 not the later one" — and the remedy is that gateways must "remember the responses to its queries and use them during replay." ([Fowler](https://martinfowler.com/eaaDev/EventSourcing.html)) **[STATED]**

**Why it is the sharpest finding for you:** your system has *two* SSOTs, the ruleset digest and the log. Anything a decision consumed that is in **neither** must be captured **into the event** or your replay is non-deterministic. That is the actual, mechanical definition of "what goes in the payload," and it is a much better rule than any granularity heuristic: **the payload is exactly the set of decision inputs and outputs not re-derivable from (pinned ruleset ∪ prior events).** Random rolls, wall-clock reads, LLM outputs, and cross-aggregate reads at decision time all fail that test and must therefore be *in* the event. **[INFERRED — the rule is my formulation; every component is STATED by Fowler/eulerfx]**

### F2. Your pinned-ruleset digest belongs *in the event's metadata*, not merely in the deployment
The documented failure — D4's "2024 logic applied to 2022 data, giving customers unintended discounts", and D2's "an upcaster can't fix a semantic change" — is the case where the payload is fine and the *interpretation* moved. **[WEAK for D4 / STATED for D2]**

**Justification for you:** you already have the defence that most teams lack (a pinned ruleset digest). But it only defends the fold if **each event records which digest was in force when it was appended.** Otherwise a replay silently folds v1 history through v2 rules and produces a state that never existed. Stamping the digest per-event converts a silent semantic drift into a loud, detectable mismatch — and it is what makes "discard on divergence" *decidable* rather than a judgement call. **[INFERRED]**

### F3. Never let an event cause an event directly — route every reaction through *view → command → decider*
Projections are documented as forbidden from emitting ("❌ Emit new events… Violations create temporal dependencies and coupling" — [Dudycz](https://event-driven.io/en/projections_and_read_models_in_event_driven_architecture/)); Event Modeling's Automation pattern gives the positive form: `Event(s) -> View -> Automated Trigger -> Command -> Event(s)` ([eventmodeling.org](https://eventmodeling.org/posts/event-modeling-cheatsheet/)). **[STATED]**

**Justification:** it is the only approach that bounds cascades *by construction* rather than by vigilance — the sole producer of events remains the decider, so every link in a chain passes through a point that can **refuse**. The documented alternative is the unbounded loop (C0). For an engine whose stated job is "triggering events and consequent event chains for every feature," this is the difference between a causal DAG and a runaway. **[INFERRED for the bounding claim]**

### F4. Rejected and proposed things must not enter the log — and the price is synchronous validation
UK GOV Publishing API [ADR-002](https://docs.publishing.service.gov.uk/repos/publishing-api/arch/adr-002-dont-log-events-which-result-in-error.html): logging error-producing requests puts "information that has no bearing on the behaviour of the system" in the log, and "an attempt to replay an event history containing rejected events would encounter errors." Their accepted consequence: **validations must occur synchronously during the request/response cycle, not asynchronously**, and the event log must update in the same transaction as the state change. **[STATED]**

**Justification:** this is the only *documented architectural decision* I found that names the exact cost of the rule, rather than just asserting the rule. If you adopt "only facts in the log," you have simultaneously adopted "the decider validates synchronously" — that is not a separate choice, it is the same choice. Note the distinction preserved: a *refusal that has business consequences* (`AttackMissed`, `SpellFizzled`, `PaymentDeclined`) is a **fact** and belongs in the log; a *malformed or unauthorised request* is not.

### F5. Snapshots cannot license truncation; only a carry-forward FACT can
Kurrent's closing-the-books preconditions are explicit: close and summarise the period, copy to cold storage, prepare read models with "summary events or aggregations [that] capture essential data needed for future rebuilds," preserve ordering metadata — and only then `truncateBefore`/scavenge, which is irreversible ("Once a scavenge has run, you cannot recover any deleted events except from a backup"). ([Keep your streams short](https://www.kurrent.io/blog/keep-your-streams-short-temporal-modelling-for-fast-reads-and-optimal-data-retention); [scavenging docs](https://docs.kurrent.io/server/v24.10/operations/scavenge)) **[STATED]**

**Justification for you specifically:** you have already declared snapshots derived-and-never-a-source. That declaration *forbids* the common "snapshot-then-truncate" move — you cannot delete the source of a derivation and keep the derivation as evidence, because on divergence you discard derived state, and then the truncated prefix is gone forever. The only consistent design is **emit a `PeriodClosed`/`CarryForward` event that is itself a fact in the log**, making the prefix genuinely unnecessary rather than merely cached. That single decision converts truncation from a data-loss risk into a modelling act. **[INFERRED — the strongest inference in this report, and the one I'd most want reviewed]**

---

## G. The design METHOD (if you want a process for writing the spec)

Two mature methods, and they answer different questions.

### G1. Event Modeling (Adam Dymitruk) — the better fit for *writing a spec*
[eventmodeling.org](https://eventmodeling.org/posts/what-is-event-modeling/), [cheatsheet](https://eventmodeling.org/posts/event-modeling-cheatsheet/) **[STATED]**

**The 7 steps:** (1) Brainstorm all state-changing events → (2) The Plot: order them chronologically and check the story holds → (3) Storyboard: attach wireframes/mockups in swimlanes per actor → (4) Identify Inputs: add **commands** (how a user triggers each state change) → (5) Identify Outputs: add **views/read models** → (6) Apply Conway's Law: group into swimlanes by team/boundary → (7) Elaborate scenarios into **Given/When/Then** for each command and each view.

**The four patterns** (each is a *vertical slice* — "the smallest possible work that can be handed over to a developer"):
| Pattern | Shape |
|---|---|
| **Command / State Change** | `Trigger -> Command -> Event(s)` |
| **View / State View** | `Event(s) -> View` |
| **Automation** | `Event(s) -> View -> Automated Trigger -> Command -> Event(s)` |
| **Translation** | `Event(s) (source system) -> View -> Automated Trigger -> Command -> Event(s) (other systems)` |

**The two rules that matter most for your question:**
- **Only state-changing events go on the timeline.** "we gently introduce the concept that only state-changing events are to be specified." This is a mechanical filter for "what IS an event."
- **Information completeness:** "every field accounted for" — trace each field's origin and destination through events; a view immediately reveals a field that has no source. This is the *checkable* version of F1.

### G2. EventStorming (Alberto Brandolini) — the better fit for *discovering* the domain
[eventstorming.com](https://www.eventstorming.com/) **[STATED]**
Three levels: **Big Picture** (understand the business domains; orange stickies = domain events on a timeline; output is "a large map of the group's understanding of the business at the time of the modeling, **never a final result**"), **Process Level** (toolbox expands to Event, Policy, Command, Read Model), **Design Level** (bridge to software design — aggregates appear). **Pivotal events** mark the phase boundaries that later become context boundaries.

**[INFERRED] Recommended combination for you:** EventStorming to *find* the events and the pivotal boundaries (it is a discovery format and tolerates being wrong); Event Modeling to *write the spec* (it is a blueprint format with slices, GWT, and information completeness). O'Sullivan's granularity remedy — "Talk to the domain expert… event storming sessions to discover actual business message boundaries" — is the same recommendation from the granularity side.

---

## H. What I could NOT establish

1. **Greg Young's book text itself.** Leanpub served only the table of contents; the chapter bodies ("Why can't I update an event?", "Weak Schema", "Copy and Replace", "Versioning of Process Managers") were not retrievable. Everything attributed to Young here comes from **secondary notes and forum posts**, and the "copy-and-replace" and "double-write" strategies are named in the ToC but I have **not** verified their content. Treat all Young attributions as second-hand.
2. **The Debezium ES-vs-CDC page** returned HTTP 403 on direct fetch; its quotes here come from the search engine's extract of that page and are unverified against the source body.
3. **The SSENSE-TECH "Evolving Your System"** article is paywalled; the exchange-rate example is corroborated in substance by Fowler but I could not read SSENSE's own version.
4. **No verifiable, attributable post-mortem** of an event-sourcing failure with a company name and date. The war-story material (D4, C0) is anonymised blog content — plausible and shape-consistent, but not evidence. The HN thread's $50–100M account is likewise an unverifiable practitioner claim. **If the design round needs an evidence-grade incident, it does not exist in the open literature I could reach.**
5. **Whether game/simulation systems specifically need vector clocks** — deliberately not pursued in depth; it borders the sibling agent's territory. What I established is the engineering shape only: within a single-writer stream a per-stream version *is* a Lamport clock and vector clocks buy conflict detection you have designed away; the lockstep-determinism literature ([Gaffer On Games, Deterministic Lockstep](https://gafferongames.com/post/deterministic_lockstep/), [Floating Point Determinism](https://gafferongames.com/post/floating_point_determinism/)) is relevant to *replay* determinism — fixed-point math, identically seeded RNG advanced in the same order, and the documented desync sources (uninitialised memory, hash-map iteration order, system time) — but I have not applied it to your design.
6. **A documented consensus on granularity.** There isn't one. E6 documents a live disagreement between two production write-ups. My reconciliation in E6 is inference, not a citation.
7. **Whether "single writer for replay reconstructability" is a documented rationale.** The literature I found consistently ties single-writer to *optimistic concurrency* (`expected_version`, `UNIQUE(stream_id, version)`). Your stated rationale — reconstructability rather than concurrency — I found **no source arguing for or against**. It is not contradicted; it is simply unaddressed.

---

## Source list

Canon / primary:
- Fowler, [Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html) · [Domain Event](https://martinfowler.com/eaaDev/DomainEvent.html) · [What do you mean by "Event-Driven"?](https://martinfowler.com/articles/201701-event-driven.html)
- Young, [Versioning in an Event Sourced System](https://leanpub.com/esversioning) (ToC only) · [community notes](https://github.com/luque/Notes--Versioning-Event-Sourced-System)
- Dahan, [Don't Delete — Just Don't](https://udidahan.com/2009/09/01/dont-delete-just-dont/) · [Clarified CQRS](https://udidahan.com/2009/12/09/clarified-cqrs/)
- Dymitruk, [What is Event Modeling](https://eventmodeling.org/posts/what-is-event-modeling/) · [Cheatsheet](https://eventmodeling.org/posts/event-modeling-cheatsheet/)
- Brandolini, [EventStorming](https://www.eventstorming.com/)

Practitioner / pattern:
- [Command vs Event (Kurrent/Dudycz)](https://www.kurrent.io/blog/whats-the-difference-between-a-command-and-an-event/)
- [Command Sourcing vs Event Sourcing (eulerfx)](https://gist.github.com/eulerfx/11227933)
- [Passive-Aggressive Events](https://event-driven.io/en/passive_aggressive_events/) · [Property Sourcing](https://event-driven.io/en/property-sourcing/)
- [Saga and Process Manager](https://event-driven.io/en/saga_process_manager_distributed_transactions/) · [Projections and Read Models](https://event-driven.io/en/projections_and_read_models_in_event_driven_architecture/)
- [Simple events versioning patterns](https://event-driven.io/en/simple_events_versioning_patterns/) · [Outbox/Inbox and delivery guarantees](https://event-driven.io/en/outbox_inbox_patterns_and_delivery_guarantees_explained/) · [GDPR in EDA](https://event-driven.io/en/gdpr_in_event_driven_architecture/)
- [Consumers, projectors, reactors (Emmett)](https://www.architecture-weekly.com/p/consumers-projectors-reactors-and)
- [Keep your streams short](https://www.kurrent.io/blog/keep-your-streams-short-temporal-modelling-for-fast-reads-and-optimal-data-retention) · [Snapshots in Event Sourcing](https://www.kurrent.io/blog/snapshots-in-event-sourcing/) · [Scavenging](https://docs.kurrent.io/server/v24.10/operations/scavenge) · [Event streams / metadata](https://docs.kurrent.io/server/v22.10/streams)
- CodeOpinion: [Domain Events in Event Sourcing? Not Exactly!](https://codeopinion.com/domain-events-in-event-sourcing-not-exactly/) · [Anti-patterns in EDA](https://codeopinion.com/beware-anti-patterns-in-event-driven-architecture/) · [Top patterns for EDA](https://codeopinion.com/my-top-patterns-for-event-driven-architecture/)
- [Marten: Events Versioning](https://martendb.io/events/versioning)
- [Arkency: correlation & causation ids](https://blog.arkency.com/correlation-id-and-causation-id-in-evented-systems/) · [Rails Event Store](https://railseventstore.org/docs/core-concepts/correlation-causation)
- [Battermann: 12 Things You Should Know About Event Sourcing](https://blog.leifbattermann.de/2017/04/21/12-things-you-should-know-about-event-sourcing/)
- [GOV.UK Publishing API ADR-002](https://docs.publishing.service.gov.uk/repos/publishing-api/arch/adr-002-dont-log-events-which-result-in-error.html)
- [microservices.io: Transactional outbox](https://microservices.io/patterns/data/transactional-outbox.html) · [Idempotent consumer](https://microservices.io/patterns/communication-style/idempotent-consumer.html)
- [Stripe: Designing robust and predictable APIs with idempotency](https://stripe.com/blog/idempotency)
- [Protobuf best practices](https://protobuf.dev/best-practices/dos-donts/) · [Enum behavior](https://protobuf.dev/programming-guides/enum/) · [Buf breaking rules](https://docs.buf.build/breaking/rules)
- [Aeron: Logical Clocks](https://aeron.io/docs/distributed-systems-basics/logical-clocks/)
- [Spatie laravel-event-sourcing: Replaying events](https://spatie.be/docs/laravel-event-sourcing/v7/advanced-usage/replaying-events)
- [Gaffer On Games: Deterministic Lockstep](https://gafferongames.com/post/deterministic_lockstep/) · [Floating Point Determinism](https://gafferongames.com/post/floating_point_determinism/)

Critics:
- [Chris Kiehl: Event Sourcing is Hard](https://chriskiehl.com/article/event-sourcing-is-hard) · [HN discussion](https://news.ycombinator.com/item?id=19072850)
- [Libutzki: Why Event Sourcing is a microservice anti-pattern](https://dev.to/olibutzki/why-event-sourcing-is-a-microservice-anti-pattern-3mcj)
- [Debezium: Event Sourcing vs CDC](https://debezium.io/blog/2020/02/10/event-sourcing-vs-cdc/) (403 on fetch)
- [codesimple: Lessons from supporting an ES system](https://codesimple.blog/2019/12/14/event-sourcing-lessons/)
- [War Stories from Production](https://dev.to/alex_aslam/when-event-sourcing-fails-war-stories-from-production-1nk2) **[WEAK]**

Granularity:
- [Barry O'Sullivan: Event Granularity](https://barryosull.com/blog/event-granularity-modelling-events-in-event-driven-applications/)
- [thisprogrammingthing: What is the correct granularity for our events?](https://www.thisprogrammingthing.com/2020/what-is-the-correct-granularity-for-our-events/)
- [I don't byte: Commands can be rejected](https://idontbyte.jaun.org/blog/2020/02/eventsourcing-notes-on-commands) · [Jonathan Oliver: Sagas, ES, and Failed Commands](https://blog.jonathanoliver.com/sagas-event-sourcing-and-failed-commands/)
