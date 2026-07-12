# Sealed Decisions — Work Assistant Mode

**Date:** 2026-07-11 · **Status:** SEALED before build. Every open question from every doc is resolved here.
A decision below is **binding**; changing one is an amendment with a review-record line, not a silent edit.

Sources swept: `00-overview` §12 · `01-data-architecture` §10 · `publish-independent-kg-indexing` §7 ·
`08` §Q15 · `09` §Q11 · `README` · the implementation plan.

---

## Part A — PO decisions (answered 2026-07-11)

### PO-1 · Platform privacy holes → **fold into Phase 1** (not a separate track)

The public-MCP domain-only scoping and the wiki's unauthenticated per-entity articles are fixed as **WS-1.2**,
inside the assistant build, not as a standalone security track.

⚠️ **Accepted risk, recorded:** these are **live holes today**, independent of this feature. Folding them in
means they stay open until Phase 1 lands. If Phase 1 slips, **re-raise this** — a security fix should not be
hostage to a feature schedule.

### PO-2 · The operator problem → **envelope encryption is a P1 requirement**

**Accepted.** Diary content is encrypted at rest with a **per-user DEK** (wrapped by a KEK in a KMS),
following the AES-GCM precedent that already exists for `usage_logs` payloads.

**Scope (P1):** diary chapter bodies (`chapter_drafts` / `chapter_revisions` / `chapter_raw_objects` /
`chapter_blocks` where `kind='diary'`) · `chat_messages.content` for assistant sessions · KG `:Fact.fact_text`
for the assistant project.

#### 🔴 What this buys — and what it does NOT (state this plainly, do not let it drift)

| Threat | Protected? |
|---|---|
| Stolen DB dump · stolen backup · a curious DBA running `SELECT *` · log/table leakage | ✅ **Yes.** This is real and is the main win |
| An operator who **controls the running server** (can read the DEK from memory/KMS, or add one log line) | ❌ **No** |

**A server-side AI pipeline requires the server to see plaintext.** That is physics, not laziness: extraction,
embedding, recall, and compaction all decrypt in-process. The only architecture that truly hides the diary
from the operator is **client-side encryption + client-side AI** — a fundamentally different product.

→ **Therefore the honest disclosure at provisioning ships anyway (P1), alongside the encryption.** Encryption
raises the bar from *"read a table"* to *"actively subvert the running application"*. We say exactly that. We
do **not** claim the operator cannot read the diary.

#### 🔴 Two concrete casualties — and how they are resolved

1. **Trigram search over `chat_messages` is impossible on ciphertext.** A GIN trigram index needs plaintext,
   and `chat_search_sessions` (WS-1.9) is **the entire week-1 recall story** (the KG is empty until entries
   accumulate).
   → **Resolution: a blind index.** Store HMAC-keyed trigrams/tokens under the user's key. Search works; the
   operator sees keyed hashes, not text. **Accepted leak:** token frequency (a known, bounded weakness of
   blind indexing). *This is net-new work in WS-1.9 — it is no longer "add a GIN index".*
2. **Embeddings.** ⚠️ **RETRACTED — the first draft called this a "limited residual exposure". It is not.**
   [Vec2Text](https://arxiv.org/pdf/2310.06816) recovers **92% of short text exactly** (BLEU 97.3) and
   demonstrably recovers **patient names from clinical notes**; training an inverter needs **no access to the
   embedding model's parameters** (just text↔embedding pairs), and [transferable attacks](https://arxiv.org/html/2406.10280v1)
   need no model queries at all. Attack cost ≈ 5M pairs / 2 days on 4 GPUs — a weekend, for exactly the
   adversary we care about. **Plaintext embeddings ≈ plaintext diary.** Encrypting `fact_text` while leaving
   embeddings readable is a deadbolt on the door with the window open.
   → **Resolution (c): encrypt the embeddings too, and brute-force cosine IN MEMORY per user at query time.**
   This works *because a diary is tiny by vector-search standards* — a few years of entries is 10k–100k
   vectors (~200MB at 1024-dim), and a brute-force scan is milliseconds. **No ANN index is needed at per-user
   scale.** Semantic recall survives and the hole closes. Defense-in-depth: adding
   [Gaussian noise](https://arxiv.org/html/2402.12784) to stored vectors sharply degrades inversion while
   barely hurting retrieval — the fallback if we ever must store them readable.

**Cost:** encryption + blind index is roughly a **medium-to-large** addition to P1, and it touches the hottest
read paths. It is now a first-class work-slice (**WS-1.0**), scheduled *before* anything that stores diary
content — retrofitting encryption after data exists is far more expensive.

### PO-3 · Trust tiers → **earn-trust auto-accept + version control**

Amends the LOCKED write-gating law:

> **Every AI write is human-gated *or* auto-accepted under an earned-trust tier — and every auto-accepted
> write is versioned and revertible with a full audit trail.**

- **Earn-trust:** after **N consistent approvals** for a given item class (e.g. high-confidence entities of a
  kind), that class auto-accepts. Facts and the diary entry stay gated longer than entities.
- **Version control is what makes it safe:** every auto-accepted write is a versioned, attributable,
  **revertible** change the user can audit and undo.

**Consequence — D17 moves earlier.** *Revert **is** the memory-amendment primitive* (amend the SSOT → re-index
→ reconcile the graph). So **D17 becomes a prerequisite for auto-accept**, not a P2 nice-to-have. **Auto-accept
does not ship until D17 ships.** Until then: per-item gating + the ≤10/day burden budget + bulk ops.

### PO-4 · Retention → **keep everything until the user deletes it**

No auto-purge of raw transcripts, diary, KG, or coach artifacts.

**Consequences, accepted and now load-bearing:**
- **Erasure (D18) is the *only* minimization story** → it is not P2 polish, it is a **release requirement**.
  The tests must assert **absence** (row gone, node gone), never "invisible".
- **Backup resurrection (T23) must be solved**: an append-only **erasure log replayed after any restore**, plus
  an honest *"erasure completes within N days"* promise matching backup retention (14d).
- **Third-party data accumulates indefinitely** → **"forget this person" (D17) is essential, not optional.**
- Blast radius of a breach/subpoena is maximal → PO-2's encryption is what carries this risk.

---

## Part B — Technical decisions (made, recorded, binding)

| # | Question | **Sealed** |
|---|---|---|
| T-1 | `user.timezone` / day-cutoff home | **auth-service `user_preferences`** (platform-wide fact; notifications/stats want it too). Not a chat column |
| T-2 | `entry_date` representation | **native `DATE`**; derive `event_date_iso` from it on write |
| T-3 | `kg_indexed_revision_id` staleness | **Own target pointer, retargeted comparison** — `last_parsed_revision_id` keeps meaning "scenes parsed for revision X"; only the revision it is compared *against* changes. One target, two independent progress markers |
| T-4 | assistant-session discriminator | **An explicit `chat_sessions.session_kind` column.** Deriving from `book_id`=diary is fragile and three consumers need it (day-window read · voice gate · search scoping) · **✅ UPHELD (2026-07-12): the human ratified this seal; D-R15's `book_id` derivation was REVERTED.** As built: `chat_sessions.session_kind TEXT DEFAULT 'chat' CHECK IN ('chat','assistant')`; the day-window read filters `s.session_kind='assistant'` (book_id is now only an optional extra scope); `CreateSessionRequest.session_kind` is enum-validated so the WS-1.10 FE stamps `'assistant'`. Tests: `test_session_kind_is_the_discriminator_not_book_id` (a diary-BOOK-bound but `session_kind='chat'` session is EXCLUDED) + create-path enum tests; full chat suite 1458 green. |
| T-5 | fact-destination policy column | `knowledge_projects.fact_destination` (`canon` \| `inbox`). **Gates Pass-1 quarantine writer too**, not just Pass-2 |
| T-6 | `is_assistant` vs `purpose` TEXT | **`is_assistant BOOLEAN`** — one home, one name |
| T-7 | glossary `captured_at` / provenance | **Yes, add it.** Day-scoped erasure of live-captured entities is impossible without it (PO-4 makes erasure load-bearing) |
| T-8 | spend-lane column shape | **generic `lane TEXT`** on `token_reservations` + `usage_logs` + `usage_outbox` (not another UUID special case) + a **daily**-window sub-cap |
| T-9 | Idle-debounce for indexing | **OFF.** Revisit only after chapter-scoped cache invalidation (WS-0.1) lands |
| T-10 | composition `prose_drift` | **Yes** — re-key to the KG pointer alongside `index_stale` |
| T-11 | Index-action MCP tool tier | **No propose→confirm.** The existing worker-ai `try_spend` guardrail + a spend estimate in the tool result |
| T-12 | `scenes` semantics after the change | `scenes` **no longer implies "published"**. Audit its readers (composition conformance · `pass2_orchestrator` · `hierarchy_writer`) and say so in the code comments |
| T-13 | Canon-search divergence | **Accept and document**: book-service lexical "canon search" stays published-only, so "canon search" and "the KG" legitimately diverge |
| T-14 | `kg_exclude` UX | **Per-chapter toggle + an indexed-state indicator.** The user must be able to see what is in their KG |
| T-15 | Passage `canon` flag on index | **`canon = (revision_id == published_revision_id)`** — draft prose never becomes canon passages |
| T-16 | Unpublish vs the index pointer | **Unpublish no longer retracts the KG** — retraction is `kg_exclude`'s job (publish means "canonical", nothing more) |
| T-17 | Coach transcripts + scorecards in erasure | **Yes** — they are the most sensitive artifacts in the feature |
| T-18 | `maintain_chain` for assistant facts | **Never passed `True`.** Its key is (subject, fact_type) — every `decision` about Alice would form one chain and blind-close unrelated decisions. Supersession is **D17's explicit amendment**, not the implicit chain |
| T-19 | BL-15 fifth onboarding intent | **"Get help with my work"** → `/assistant` + provisioning. Recorded as an explicit BL-15 amendment |
| T-20 | Which coach templates ship first | **Deferred to P5** (not blocking). Proposed: *raise a risk to your manager* · *give difficult feedback* · *run a focused 1:1* |
| T-21 | Rubric provenance + licensing | **Deferred to P5**, with the rule already locked: *an adapted rubric inherits the source's structure, **not** its validation. Ours is validated by our own eval, or it is not validated.* Check the licence before embedding |
| T-22 | Detector self-disarm threshold | **P5.** Dismiss-rate is an *operational* signal only (it selects for flattery); the quality metric is precision against a hand-labeled set |
| T-23 | Verify this doc's own citations (R3) | **Before P5 sign-off** — a spec that mandates citation integrity must pass its own gate. Unresolvable ⇒ dropped |

---

## Part C — What changed in the plan because of Part A

1. **New WS-1.0 — envelope encryption + blind index.** Scheduled **first in Phase 1**, before anything stores
   diary content (retrofitting encryption after data exists is far more expensive). WS-1.9's search is now a
   **blind index**, not a GIN trigram index.
2. **Phase 0.5 dissolved** into WS-1.2 (PO-1). The accepted risk is recorded above.
3. **D17 (memory amendment) is promoted into Phase 1/early-2** — it is the *revert* mechanism that makes
   PO-3's auto-accept safe, so **auto-accept cannot ship before it**.
4. **D18 (erasure) is a release requirement, not P2 polish** — PO-4 removed every other minimization story.
5. **Honest operator disclosure still ships in P1** alongside the encryption (PO-2's residual risk).

## Part D — RESOLVED: embeddings are encrypted too (option **c**)

Was: *"(a) accept the exposure, or (b) drop semantic recall."* **Both were wrong.** See PO-2 casualty 2 — the
exposure is not "limited", it is near-plaintext; and dropping semantic recall was never necessary, because a
**per-user** diary needs no ANN index. **Encrypt the vectors; brute-force cosine in memory at query time.**

---

## Part E — What the industry actually does (and the half we were missing)

Checked, because "how do Claude/ChatGPT protect this?" is the right question to ask before inventing something:

- **AES-256 at rest, TLS in transit — and *no* end-to-end encryption. The provider holds the keys**
  ([OpenAI enterprise privacy](https://openai.com/enterprise-privacy/)).
- **Authorized employees can access conversations** (incident response, abuse investigation, legal
  compliance), plus third-party contractors for abuse review. A flagged/sampled conversation **can be read by
  a human**.
- Retention limits (30-day deletion), and user escape hatches (Temporary Chat, memory off).

**Conclusion: nobody has solved "the operator cannot read it" while keeping server-side AI — because you
can't.** The industry's protection is **encryption-at-rest against theft + strict access control + audit +
retention + disclosure**. It is *organizational*, not cryptographic.

### What we adopt from that (the half our design was missing)

| | Decision |
|---|---|
| **Encryption** | Our per-user DEK is **at or above** the industry bar (better blast-radius containment than one provider-held key). Keep it |
| **Audit** | 🔴 **NEW REQUIREMENT — WS-1.0b: an append-only audit log of every admin/operator read of diary content.** This is the control the industry actually relies on, and we had none |
| **Retention/deletion** | User-controlled (PO-4) + D18 erasure. Already planned |
| **Disclosure** | Honest, derived from real deployment facts. Already planned |
| **The claim we are allowed to make** | *"Encrypted at rest with your own key. An administrator who controls the server could still access it — and every such access is logged."* **Never** *"we cannot read your diary."* |
