# S-05 UI/UX audit + GUI scorecard (user-perspective, 2026-07-18)

> Role: a **novelist using the app**, NOT the developer. Method: trace every S-05 interaction as a
> first-time user would hit it. Surfaces audited: (A) fact authoring/invalidation on the entity-detail
> slide-over, (B) the `kg-triage` queue panel, (C) the triage nudge on the KG overview.
> Layout verdict is **code-assessed** (flex/tailwind structure) — not pixel-verified live; a full live
> pass needs the new BE image + seeded triage/fact data (the running stack is the pre-S-05 image).

## Business-flow walk-through (what actually happens when I click)

**A. "I want to record a fact about a character."**
studio → open **KG entities** → click a character → slide-over → scroll to **Known facts** → **+ Add fact**
→ inline form (type dropdown, text box, two small boxes) → **Save fact** → it appears. ✅ works end-to-end.
Mark a fact wrong: click the ⃠ icon on a fact → **an OS confirm box pops** → invalidated, disappears.

**B. "Extraction flagged things that don't fit my schema."**
studio → **Triage** (palette, or the "N need triage →" nudge on KG overview) → grouped list → each row shows
a warning + a label + a snippet + action buttons → click an action. Dismiss/Map/Add-to-schema/Add-to-vocab/
Promote-to-glossary all complete. **"Fix endpoint" (re_target) pops an OS prompt asking for a "Corrected
target entity id".**

## Findings (severity-ranked)

### 🔴 Dead button — a feature you cannot actually use
- **F1 · `re_target` ("Fix endpoint") prompts for a raw entity UUID.** `window.prompt("Corrected target
  entity id")` — a novelist has NO way to know an entity's UUID, and there is no picker/search/list. The
  "fix this relationship's endpoint" path is unusable by a human. For an `edge_kind_mismatch` row the only
  *other* offered action is **Drop**, so in practice the user can only delete, never fix. This is the exact
  "have a feature but no way to actually use it" pattern. **Fix:** replace the prompt with an entity picker
  (search-select), or hide `re_target` until one exists.

### 🟠 Breaks the app's own modal system / leaks machine data
- **F2 · OS dialogs everywhere.** `window.prompt` for `re_target`/`map`; `window.confirm` for **mark-fact-
  wrong** and for the **schema-write** confirm. Raw browser boxes — inconsistent with the app's Radix
  dialogs, un-themeable, and (the sample scorecard's words) "break the spell." 3 sites.
- **F3 · Raw JSON shown to the user.** The triage evidence line falls back to `JSON.stringify(payload)`
  (e.g. `{"predicate":"rules_over","subject_id":"a3f2…"}`), and the per-item **drill-in row ALWAYS renders
  raw JSON** (`JSON.stringify(it.payload).slice(0,90)`). A novelist sees code, not their story.
- **F4 · `map` prompts for a raw schema code** (`map_to`). Less blocking than F1 (blank falls back to the
  detected value, and add-to-vocab/dismiss are alternatives) but still a raw-identifier prompt.

### 🟡 Jargon — assumes ontology/DB literacy a novelist doesn't have
- **F5 · Fact form leaks triple-store terms.** The two optional boxes are placeholdered `"predicate
  (optional, e.g. loyal_to)"` and `"object (optional, e.g. House Vaeth)"`. "predicate"/"object" mean nothing
  to a writer.
- **F6 · Fact-type taxonomy is ambiguous for story facts.** decision / preference / milestone / negation /
  statement / commitment. For "Aria distrusts the Council" — is that a *statement*? a *negation*? The user
  must guess; there's no hint of what each means.
- **F7 · Triage labels are KG jargon.** "Fix endpoint", "Widen allowed kinds", "Off-vocabulary value",
  "Relationship endpoint mismatch", "Close previous", "Set multi active". Correct to an ontologist, opaque
  to a novelist.

### 🟡 CRUD / affordance gaps
- **F8 · Facts have no UPDATE + no hint that there isn't one.** Create ✅ / Read ✅ / Delete ✅ (mark-wrong),
  but no "edit fact" — by design (bitemporal: invalidate + re-assert), yet the UI never says so. A user with
  a typo in a fact finds no edit button and no guidance to "mark wrong, then re-add."
- **F9 · Mark-wrong is irreversible from the UI (no undo, no history).** The entity **archive** action
  offers an Undo toast + a restore route; **fact invalidate does not** — once marked wrong the fact vanishes
  with no "show invalidated" toggle and no undo. Asymmetric with the sibling archive UX.

### 🟡 Reachability / discoverability
- **F10 · "+ Add fact" is buried.** Only visible after opening an entity's slide-over and scrolling to the
  facts section; and it requires the entity to already exist (no path to jot a fact about a character the
  extractor hasn't found yet without first creating the entity elsewhere).
- **F11 · Empty triage panel gives no orientation.** "Nothing to triage — every extracted element matched
  your schema." is a fine empty state, but a user who opens Triage out of curiosity gets no explanation of
  *what* triage is or *when* it fills.

### 🟢 Verified OK
- **F12 · No dead loops; no lost data.** Owner-scoped; optimistic refetch; every surface has loading/empty/
  error states; the live Neo4j smoke confirmed author→show, tenant isolation, invalidate→drop.
- **F13 · Layout (code-assessed): low overlap risk.** Action buttons `flex-wrap`; evidence `truncate`; form
  inputs `w-full`. The one cramped spot is the two side-by-side predicate/object inputs on a ~375px mobile
  slide-over (~150px each) — tight but not broken. Not pixel-verified live.
- **F14 · Triage panel IS reachable** (palette + overview nudge) and every RENDERED button now completes a
  real backend action (the misleading schema-only-intent buttons were removed / wired this session).

## 🎯 GUI Scorecard — S-05 (fact authoring + KG triage)

| Metric | Score | Why |
|---|---|---|
| **Usability** (can I do the job?) | **6.5/10** | Fact author→show→mark-wrong works; triage dismiss/map/add-to-schema/add-to-vocab/glossary-handoff work. Docked hard by **re_target = a dead UUID button** (F1). |
| **Completeness** (CRUD) | **7/10** | Facts C/R/D ✅ (U absent by design but unsignposted, F8). Triage resolve/dismiss/per-item-dismiss ✅; add-to-vocab/add-to-schema now WRITE. re_target unusable. |
| **Ease of use / learnability** | **5/10** | Inline forms + drag-free flows are simple, but **jargon** (predicate/object, six fact types, "endpoint"/"vocab") makes a novelist guess (F5–F7). |
| **Beauty / aesthetics** | **5.5/10** | Cards, warning-amber, chips, count badges are on-brand — until **raw JSON** (F3) and **OS prompt/confirm boxes** (F2) appear and break the spell. |
| **Consistency** | **5.5/10** | mark-wrong uses `confirm()` while entity-archive uses a toast+Undo; triage uses `prompt()` while the app uses Radix dialogs; "predicate/object" vs the app's plain voice. |
| **Accessibility / multi-device** | **6/10** | Good a11y tree (aria-labels, testids, a mobile square tap target on mark-wrong). But a **UUID prompt is hostile to everyone**, evidence is tiny 11px, and the fact ⃠ icon is small. |
| **Robustness** | **8/10** | No expected console errors; owner-scoped; optimistic refetch consistent with server; all states handled; live-smoke green. |
| **Discoverability** | **6/10** | Triage now reachable (nudge+palette); "+ Add fact" is buried in a slide-over; empty triage offers no orientation (F10–F11). |
| **🎯 Overall** | **≈ 6.1/10** | A **real, operable** feature — not a hollow shell (this session killed the empty-shells + zero-callers). But it ships one **dead UUID button** (re_target), three **OS-dialog** rough edges, **raw-JSON** leaks, and **KG jargon** that would confuse the novelist it's built for. |

## Top-5 fixes to raise the score (recommended order)
1. **F1 re_target entity picker** (kills the only dead button) — biggest usability jump.
2. **F2 replace the 3 OS dialogs** with the app's Radix confirm/dialog + an inline entity/target picker.
3. **F3 humanize the triage evidence** — render `predicate`/`value`/`kind` as a sentence, never raw JSON.
4. **F5–F7 de-jargon** — rename the fact-type + triage labels + the predicate/object placeholders to a
   novelist's language (or add helper text).
5. **F9 fact mark-wrong Undo** (mirror the entity-archive toast+restore) + **F8** a one-line "to fix a fact,
   mark it wrong and add the corrected one."
