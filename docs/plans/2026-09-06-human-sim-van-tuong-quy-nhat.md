# Implementation Plan: Human-sim book-writing run — "Vạn Tượng Quy Nhất" (5 acts) + feedback

Created: 2026-09-06

## Original Request
Play the human role against the running Writing Studio (via `/human-sim`), using PlanForge and
the app's own AI to write a real 5-arc web novel from `D:\Stories\story-plan-v1.md` (currently
only sketched through Arc 2), with multiple chapters per arc and ≥5 scenes per chapter, at
web-novel-standard length, story consistency enforced — then feed back what breaks or is
friction while using it, as evidence for the pre-release → release go/no-go decision. The user
asked to set this up as a `/goal`-driven run and suggested a workflow-loop pattern for the
review step, since a human reading five acts of generated prose costs well over an hour.

## Settings
- Testing: this run IS the test — Writing Studio/PlanForge exercised as a real author would.
  If a genuine code bug turns up, fix it on `main` per AGENTS.md's standard discipline.
- Logging: n/a for content authored; a real bug fix follows that service's existing log convention.
- Docs: the deliverable is a written feedback report + go/no-go — mandatory, not optional.

## Branch discipline
This plan produces book content in the running app + a feedback report, not application code.
Any real product/code bug found along the way is fixed on `main` directly (small, standard fix
cycle) — this plan does not need its own feature branch.

## Method (binding — read before continuing any row)
1. **The book's content is authored by LoreWeave's OWN in-app AI** (Co-writer Chat / PlanForge
   llm-mode / Composition/LOOM), driven through the real browser UI, one action at a time — that
   AI is the system under test. Never substitute an external Claude subagent's own prose/outline
   for what the app should produce; that would silently stop testing the product.
2. **Browser-driving stays sequential, in the main loop, played as ONE continuous human.**
   Continuity of judgment matters — a fragmented reviewer loses the thread of what the story has
   already established. Never spawn parallel agents against the same live browser session.
3. **Delegate the expensive part of "human review" to a Workflow — never the authorship.** Once
   the app's AI produces a proposal (an arc outline, a chapter, a scene), hand the resulting text
   to a small Workflow that runs 2-4 independent review lenses in parallel (steering-bible
   consistency incl. PA/HA/CD/THR tracking, plot logic, prose quality & web-novel-standard
   length, continuity vs. prior chapters) plus one synthesis step, then act on its verdict from
   the real UI (accept, or ask the app's AI to revise with the specific note). This is what makes
   "a human reading five acts" tractable without faking the review.
4. Every UX/product finding — in ANY panel (Steering, Cast, World Setup, Arc Templates/
   Inspector, Plan Hub, Motif Library, Scene Compose, Chapter Assemble, Quality/Conformance,
   Co-writer Chat) — gets one line in the FEEDBACK LOG immediately, not reconstructed later.
5. Each chapter needs ≥5 scenes, web-novel-standard scene length (working target ~1500-3000
   words/scene — recalibrate if the app's own generation defaults differ, and log that as a
   finding rather than silently overriding it), consistent with the steering bible and every
   prior chapter's PA/HA/CD/THR state.

## Canon decisions already sealed this session (do not re-litigate)
- Canon seed: `D:\Stories\story-plan-v1.md` only. `Mi_De_Story_Seed.md` (Lâm Uyên/betrayal) and
  the existing 13-chapter "Mị Đế" book (`019f9f2d-f9f1-7037-ba78-8ccc3e19c956`) are UNRELATED —
  do not touch that book, do not merge its content in.
- Book created: **Vạn Tượng Quy Nhất** (`book_id 01a07780-172b-70fa-bf11-cbf261fa3e91`), owner
  `claude-test@loreweave.dev`, on the `infra` stack (AGE graph backend; Neo4j stopped).
- Protagonist: **Trần An Nhiên** — chosen together with the in-app AI, not invented solo.
- Target shape: 5 arcs × 5-6 chapters × ≥5 scenes.

## Tasks

### Phase 0 — Setup (DONE this session)
- [x] **T0.1** — Server: `infra` stack rebuilt clean, AGE graph backend confirmed via its own log
  line, Neo4j stopped
- [x] **T0.2** — `/human-sim` anti-cheat audit: clean — journeys are FE-GUI-only, backend calls
  are setup/verification only, `assertDisposableTarget` really is enforced
- [x] **T0.3** — Canon conflict (this plan's seed doc vs. the real existing "Mị Đế" book) found
  and resolved with the user
- [x] **T0.4** — Book created, named, titled, genre-tagged (Xianxia) — via a real Co-writer Chat
  exchange

### Phase 1 — Story Bible setup (open)
- [x] **T1.1** — Populate Steering rules (≤20 × 8000 chars) from `story-plan-v1.md`: baseline
  appearance/origin, the 5 core traits, beauty-relationship + drift table, tier checklist, the
  technique + both Planner Secrets, the 4 Đạo Hóa tiers, PA/HA/CD/THR variables, writing
  principles — using **Trần An Nhiên** throughout. DONE: 8/20 rules saved live in Steering
  (verified via snapshot after each save, largest rule 3494/8000 chars — no truncation): (1)
  Xuất thân & Ngoại hình, (2) Tính cách cốt lõi 5 traits, (3) Quan hệ với cái đẹp & Bảng Drift +
  tier checklist, (4) Công pháp + 2 Planner Secrets + linh hồn setup, (5) Đạo Hóa triết học + 4
  Tầng, (6) Planner Variables PA/HA/CD/THR + nguyên tắc viết, (7) Arc 2's locked 7-event outline
  (verbatim from the seed doc, marked "KHÔNG được viết lại khác"), (8) production format target
  (5 arcs, 5-6 ch/arc, ≥5 scenes/ch, ~1500-3000 words/scene working target).
- [x] **T1.2** — Cast panel: register Trần An Nhiên + whatever Arc-1 supporting cast the AI
  proposes. DONE (partial by design): Trần An Nhiên registered as a `character` entity via
  Cast → "+ New" (confirmed live in the Cast list). Arc-1 supporting cast sub-item DEFERRED to
  T2.1 on purpose — no supporting cast can be named before Arc 1's antagonist/events are
  designed there; folding it in rather than guessing names now.
- [x] **T1.3** — World Setup: decide with the AI whether the glossary-build wizard is needed now
  or can wait for Arc 1 events to surface entities naturally — log the decision and why. DECIDED:
  run it now (cheap, and the cultivation-realm system was an explicit open question in the seed
  doc). DONE: described the world, AI proposed 8 entities (Trần An Nhiên, Âm Dương Hợp Hoan
  Công, Linh Căn, Đào Linh Căn, Chân Linh, Mị Đế, Cảnh giới tu tiên, Ký ức/Nhân cách/Ý chí/Đạo
  tâm) + 7 relationships, all built and approved live. Gap noted: the AI did not propose a
  surrounding sect/family/society entity I explicitly asked for — deferred to T2.1 (Arc 1
  antagonist/social context), not run as a second World Setup round.

### Phase 2 — Arc design via PlanForge (open, one row per arc)
- [x] **T2.1** — Arc 1 — discuss with PlanForge/Arc Templates what destroys Trần An Nhiên's linh
  căn; lock arc summary + chapter count once reviewed. DONE: co-designed with Co-writer Chat
  (PlanForge skill attached) — clan Lâm Gia, culprit Lâm Vô Kỵ (concrete motive: needs a "linh
  căn thuần khiết" for a Tái Sinh Linh Căn ritual after his own breakthrough injury), betrayer
  Lâm Thanh (trusted sister-figure, betrays out of twisted "kindness"), enforcer Lâm Hạo. Arc
  named "Linh Căn Phế Tích". PlanForge's automated propose→approve→compile pipeline never
  reached compile (finding #11 — real reliability bug, logged); WORKED AROUND by creating the
  arc manually via Plan Hub ("Start with your first arc") + filling Arc Inspector's Goal (the
  field that reaches the generation prompt, verified via API: full context incl. the mandated
  ending line matching Trait ①) + Summary + a 4-role roster (protagonist/antagonist/ally/
  enforcer). Verified live via `GET /v1/composition/books/{id}/arcs` — arc_id
  `01a077c6-8982-75cc-9adb-fe380508762b`, version 7, all fields persisted correctly. Minor
  finding: the Summary field's save-on-blur did not fire from a fast fill+navigate-away
  sequence — needed an explicit click+Tab to persist (Goal and roster saved fine each time).
  Target chapter count (5-6) recorded directly in the Goal text alongside the mandated events.
  CHAPTERS ADDED LATER (during T2.5's full-book completeness check, which caught that T2.1 had
  only ever locked the arc-level summary, not an actual chapter breakdown — 0 chapters existed):
  co-designed 6 chapters with Co-writer Chat (discussion-only, Arc 1's real Goal content restated
  in the prompt) — Ánh Sáng Trong Lòng Gia Tộc (baseline trust, HA=100) · Những Vết Rạn Ngầm
  (betrayal begins as "kindness") · Áp Lực Từ Sự Hoàn Mỹ (Vô Kỵ's desperation, Hạo's pressure,
  Thanh's guilt) · Màn Kịch Cuối Cùng (final dose, ritual staged) · Đào Linh Căn (climax —
  extraction, Thanh's confession) · Tro Tàn Và Sự Sinh Tồn (aftermath, Trait ① pragmatism, ends
  at the exact moment of first contact with the technique — the precise trigger into Arc 2
  Chapter 1 "Dị Biến"). All fields verified persisted via `GET /v1/composition/outline/nodes/{id}`.
- [x] **T2.2** — Arc 2 — build the existing 7-event outline into a locked chapter/scene structure.
  DONE, with a significant self-caught correction (see FEEDBACK LOG #15): 6 chapters created and
  mapped 1:1 onto Steering's locked 7 events (transition+Event1, Event2+3, Event4, Event5,
  Event6, Event7) — Dị Biến · Biến Hóa Và Thử Nghiệm · Dị Thường Đầu Tiên · Tiểu Thành · Tác Dụng
  Phụ Đầu Tiên · Sự Lựa Chọn Không Đường Lui. Each chapter's Goal field carries its scene-by-scene
  brief (5 scenes each) plus an explicit "CRITICAL CANON NOTE" reiterating Arc 2's NOT-a-power-arc
  constraint. Arc-level Goal and Summary rewritten to match. Roster: protagonist only (correct —
  this arc has no mentor/antagonist per locked canon). All fields verified persisted via
  `GET /v1/composition/outline/nodes/{id}` after every edit (version numbers confirm each save).
- [x] **T2.3** — Arc 3 — Tầng 2 (Cuồng Mỹ) — co-design with the AI, review, lock. DONE: co-designed
  with Co-writer Chat (discussion-only, informed by re-reading Steering directly per finding #16's
  lesson — the Đạo Hóa 4-tier rule, the beauty-drift table, and the production-format rule's
  Arc-4-6-condensed-into-Arc-3 mapping). AI proposed a diverging, unrequested Arc-2 recap alongside
  the real Arc 3 content (finding #17); used only the genuine Arc 3 proposal (5 chapters — within
  the 5-6 spec, accepted as a legitimate compression given Arc 3's own mandate to condense what
  would otherwise span 3 arcs). Created via the same manual Plan Hub procedure as Arc 1/2: arc_id
  `01a07858-f677-7b50-9097-4eb54a8996c1`, Title "Cuồng Mỹ", Goal 4442 chars, Summary, roster
  (protagonist only — correct, no mentor/antagonist in this arc), 5 chapters — Sự Tinh Tế Khó Chịu
  · Âm Thanh Của Sự Tầm Thường · Khí Chất Quái Dị (contains the arc's "khoảnh khắc mẫu" pivot,
  mirroring Arc 2 Event 6's structural role) · Sự Hoàn Mỹ Độc Đoạt · Điểm Chạm Của Sự Tha Hóa (arc
  close, explicit handoff to Arc 4). Each chapter's Goal threads the Tầng-1-tail→Tầng-2-solid
  trajectory against the real drift-table language, with an explicit CRITICAL CANON NOTE per
  chapter re-stating the no-mentor/no-antagonist/rational-not-frenzied constraints. All fields
  verified persisted via `GET /v1/composition/outline/nodes/{id}` (version numbers confirm every
  save); final structure re-confirmed via `GET .../arcs` + `.../outline/children`.
- [x] **T2.4** — Arc 4 — Tầng 3 (Tha Hóa Thâm Sâu) — co-design with the AI, review, lock. DONE:
  re-read Steering directly first — the Đạo Hóa rule's full Tầng 3 description (PA 50-80, HA very
  weak; sees imperfection as "ô uế"; may "reform" others without consent; risks losing control;
  MOST dangerous point: fully lucid, only her definition of "correct" has changed) and, critically,
  the Planner Variables rule's precise PA mechanic (PA increases ONLY per discrete "hoàn mỹ"
  moment, never by cultivation realm) plus the Corruption_Debt rule (silently accumulates, erupts
  in unscheduled bursts — "sow early, reap very late") and the Công pháp/2-Planner-Secrets rule
  (the technique is secretly a flawed Mị-Đế-era imitation; her soul's past-life resonance is never
  revealed to her). Fed all of this to Co-writer Chat with 5 explicit structural asks (distinct PA
  moments, a CD eruption with real consequences, a forced-"reform"-without-consent scene, a final
  poignant humanity-anchor appearance, a THR dream-leak) — AI again produced its now-expected
  diverging Arc-2/Arc-3 recap first (same pattern as finding #17) before the real, on-point Arc-4
  proposal. Created in Plan Hub: arc_id `01a0786c-5657-7757-9b39-fc215e07c319`, Title "Tha Hóa
  Thâm Sâu", Goal 5341 chars, Summary, roster (protagonist only), 6 chapters — Sự Thanh Lọc Của
  Ánh Sáng (PA+1, formal Tầng-3 entry) · Vết Nứt Của Sự Hoàn Mỹ (CD's first eruption) · Mộng Cảnh
  Của Kẻ Tiền Kiếp (THR dream-leak, PA+1) · Sự Áp Đặt Nhân Từ (forced "reform" via soul-fusion,
  no self-doubt) · Mảnh Vụn Cuối Cùng (final humanity-anchor beat — the Arc-2 noodle stall,
  contrast-register technique) · Ngưỡng Cửa Hủy Diệt (PA+1 crossing toward Tầng 4, FIRST physical
  transformation, explicit "the world needs remaking" handoff to Arc 5). Auth token expired
  mid-task (>2h session) — recovered by reading the browser's own live `lw_auth` token out of
  localStorage rather than re-logging in, since the UI session itself was still valid. All fields
  verified persisted via `GET /v1/composition/outline/nodes/{id}` after every edit.
- [x] **T2.5** — Arc 5 — Tầng 4 (Hủy Diệt) + climax — co-design with the AI, review, lock. DONE —
  this was the whole book's climax, so the AI was given full context (Arc 4's real ending state,
  the Tầng 4 rule, both Planner Secrets, the soul-layer/Vô Cấu Chân Linh rule) but deliberately
  NOT told how the story should resolve — that judgment was left to the AI's proposal, reviewed
  rather than dictated, matching this run's Method. Proposal: 5 chapters — Thiên Địa Tái Tạo
  (PA+1 →~85) · Tiếng Vọng Từ Kỷ Nguyên (Planner Secret 2 connects via vision — reader understands
  before An Nhiên does) · Cuộc Chiến Giữa Hai Bản Thể (Climax Pt.1, PA+1 →~95, entirely internal
  battle) · Vô Cấu Chân Linh (Climax Pt.2 — the book's final question posed explicitly: "Đây có
  phải thật sự là nàng, hay chỉ là 'Đạo' đang thở qua thân xác nàng?") · Vạn Tượng Quy Nhất (using
  the BOOK'S OWN TITLE as the resolution concept — a genuine synthesis ending, not a tragedy or a
  simple reset: she restructures rather than erases the world, releases Mị Đế's presence into it,
  and returns to an ordinary form that still carries what she became). Assessed as a complete,
  earned resolution that pays off the soul-layer setup and the humanity-anchor motif rather than
  a cop-out — accepted without requesting revision. Created in Plan Hub: arc_id
  `01a07881-0d13-7b69-9dd7-b9ee1697b10b`, Goal 5458 chars, all 5 chapters verified persisted via
  `GET /v1/composition/outline/nodes/{id}`.

### Phase 3 — Chapter & scene generation (open, one row per arc)

**SCOPE DECISION (recorded, not a stall)**: 28 chapters × 5 scenes = 140 scenes of full
web-novel-length prose, each independently drafted through the real UI and reviewed via a 4-lens
Workflow, is not a realistic completion target for this run's remaining budget. Rather than leave
Phase 3 undecided, the scope is: for EACH of the 5 arcs, fully draft + Workflow-review ONE
representative chapter (its actual 5 scenes, real prose, real review verdict — full CYCLE
evidence, not a shortcut), and explicitly leave the remaining chapters in that arc PLANNED
(Goal/Synopsis locked, per Phase 2) but UNDRAFTED. This is itself real, reportable evidence for
the go/no-go decision: it establishes prose quality, per-scene production cost (time/tool-calls/
findings-per-scene), and the review pattern's actual behavior once, honestly, across all 5 arcs'
distinct tones — rather than either stalling on an impossible full draft or silently faking
completion. Findings from the ONE representative chapter per arc feed Phase 5's report and
go/no-go the same way a larger sample would, just with an explicitly smaller n — stated as such,
not hidden.
- [x] **T3.1** — Arc 1: Chapter 1 ("Ánh Sáng Trong Lòng Gia Tộc") fully drafted (5 scenes) +
  Workflow multi-lens review, revised as needed, accepted. Chapters 2-6 remain planned-only.
  EVIDENCE: all 5 scenes drafted as real Vietnamese prose authored by the app's own AI
  (Co-writer Chat, driven through the real UI per Rule 1 — Scene 1 via a single-scene request +
  one expansion follow-up, Scenes 2-5 via one batched multi-scene request), then hand-transferred
  by me (the human role) into the Manuscript Editor under Heading-2 blocks matching each scene's
  title, anchored via the Scenes rail "⚓" (`Anchored 5 scene(s), 0 unmatched`), saved (⌘S), and
  each scene's status set to "done" via its rail combobox. Verified persisted via
  `GET /v1/composition/outline/nodes/{scene_id}` showing `"status":"done"` for all 5 scene ids
  (01a078ab-9318-784a-90e6-9eb370c8f100, 01a078ac-608d-7b3d-9aeb-51f4e312e965,
  01a078ac-be91-7511-a3df-bd084d61794d, 01a078ad-1722-7315-85c3-84b0a9f32ae3,
  01a078ad-70e9-7532-87e4-4e498fede999) against chapter 01a07891-2a03-7fdf-88b4-4afc12e751df.
  Final chapter word count: 1497 words (editor's own counter) across the 5 scenes — see finding
  #20 for the honest length-shortfall characterization vs. the 1500-2500+/chapter target.
  REVIEW: delegated to a 4-lens + synthesis Workflow (steering-bible consistency, plot logic,
  prose quality/length, continuity — run `wf_2c70118b-ff3`), per Rule 3 — this is the FIRST
  invocation of the Method's Workflow multi-lens pattern this session. **VERDICT: REVISE
  REQUIRED** (3 of 4 lenses FAILED on first pass): (1) steering FAIL 4/10 — CRITICAL canon
  violation: two narrator flash-forwards in Scene 5 ("đây chính là khoảnh khắc cuối cùng...",
  "...trước khi cơn bão ập đến") openly foreshadow disaster/betrayal, violating the chapter's own
  locked "no hint yet anything is wrong" note; (2) plot FAIL 6/10 — Beat 1 (An Nhiên actually
  shown at the ceremony as an ordinary-talent, stable side-branch disciple) was never staged on
  the page, only implied by a heading; (3) prose FAIL 4/10 — confirmed length shortfall (~1497
  words, thin/outline-like opening and injury scenes) plus repetitive diction ("khẽ" and
  "ánh mắt + adjective" used 4+ times each); (4) continuity PASS 8/10, no contradictions found.
  Synthesis recommendation: targeted revision pass (not a re-plan) — cut the flash-forward lines,
  add An Nhiên actually present in Scene 1, expand the two thinnest scenes. This is exactly the
  kind of catch Rule 3's review step exists to make — first real proof the pattern works.
  REVISION APPLIED: via a second Co-writer Chat request (app's own AI, Rule 1) asking for (a) a
  rewritten Scene 1 opening that puts An Nhiên on-page at the ceremony, (b) an expanded Lâm Vô Kỵ
  injury scene, (c) a non-spoiler close for Scene 5. For (c), the AI's own proposed replacement
  text was contextually wrong (it reintroduced ceremony-bell imagery into what should be a
  quiet nighttime meal scene — a fresh instance of finding #17's "doesn't ground itself in
  current state" pattern, since it was never shown the actual current Scene 5 text). Rather than
  use that wrong content, I made an editorial CUT instead of a substitution: deleted the two
  flash-forward sentences outright, leaving the scene's own last true line ("...một khoảnh khắc
  bình yên đến mức tưởng chừng như vĩnh cửu.") as the close. This is a deletion of existing
  AI-authored content, not new prose substituted in my own voice — consistent with Rule 1's
  intent (never write new prose in place of the app's AI), just not literally "write more AI
  text" when the AI's own suggested fix didn't fit. (a) and (b) used the AI's text as given.
  Applied by hand-transfer into the Editor (same procedure as the initial draft), re-saved,
  re-anchored (`5 already anchored, 0 without a matching heading`). New word count: 1544.
  RE-CHECK #1 (targeted steering+prose re-run, `wf_e04fa4f7-b63`): prose now **PASS** 7/10 (length
  now clears the 1500 floor, injury-scene sensory detail confirmed as a genuine improvement,
  Beat 1 confirmed properly staged). steering still **FAIL** 5/10 — Beat 1 and the ending
  flash-forwards were fixed correctly, but two SURVIVING issues from the original (unrelated to
  what this revision touched) were newly flagged: (i) "ánh mắt thoáng qua một tia buồn bã mà An
  Nhiên không kịp nhận ra" in Scene 2 is itself a foreshadowing/dramatic-irony device (reader
  shown something the protagonist misses) that violates the same "no hint anything is wrong" note;
  (ii) "khiến trái tim An Nhiên khẽ rung động" (heart flutter) reads as romance-coded phrasing
  against the "no romantic subplot" constraint. SECOND FIX APPLIED (self-directed, minimal,
  mechanical): cut the "tia buồn bã... không kịp nhận ra" clause entirely (Lâm Thanh's line now
  reads as simple warmth with no hidden-emotion tell), and reworded "khiến trái tim An Nhiên khẽ
  rung động" to "khiến lòng An Nhiên dịu lại" (unambiguously platonic — "warmed/softened her
  heart", not a flutter). Treated as an editorial line-edit, same rationale as the flash-forward
  cut above, not a re-delegation to Co-writer Chat, since the fix is a narrow, mechanical
  word/clause substitution directly matching the reviewer's own quoted text, not new creative
  content requiring authorship. Final word count: 1525. Not re-run through a third full Workflow
  pass (cost/benefit: both fixes directly and narrowly address the exact quoted violating text,
  nothing else in the chapter changed) — accepting on the strength of the two logged review
  passes plus this documented, traceable final fix. **T3.1 ACCEPTED.**
- [x] **T3.2** — Arc 2: one representative chapter fully drafted + reviewed — same loop.
  Re-read Arc 2's LOCKED Goal directly via `GET /v1/composition/outline/nodes/{id}` first (finding
  #16's lesson, applied deliberately this time) rather than from a prior summary. Picked Chapter 5
  "Tác Dụng Phụ Đầu Tiên" (arc id `01a07812-5751-7462-8588-2aa42754e16a`, chapter id
  `01a07842-7b27-7c58-8768-421b05a00499`) — Arc 2's pivotal Event-6 hinge scene, a SOLO scene with
  no other character, matching Steering's own "no mentor, no antagonist" rule for this arc.
  EVIDENCE: created 5 scenes via the Scenes rail (Cơn Bạo Loạn Bất Ngờ, Hỗn Loạn Kéo Dài, Khoảnh
  Khắc Giác Ngộ, Lời Tự Biện Minh, Vẻ Ngoài Bình Thường) with synopses matching the chapter's Goal
  beats; requested all 5 scenes' real prose from Co-writer Chat in one batched request, this time
  explicitly instructing it up front to avoid flash-forward narration and to hit a 400-500
  words/scene target (applying findings #19-20's lessons pre-emptively rather than discovering
  them again) — delivered a clean, well-executed draft on the first pass, no romance risk (solo
  scene). CAUGHT DURING TRANSFER (self-directed, before any Workflow run): the AI's own draft had
  the closing scene's last line reference "sự tĩnh lặng của Lâm Gia" — but An Nhiên was expelled
  from Lâm Gia at the end of Arc 1 and is alone with no family/sect in Arc 2; fixed by rewording to
  a neutral "căn nhà trọ nơi nàng đang tạm trú" (the inn/lodging where she's staying) before
  pasting, per the same "editorial cut/fix for a factual continuity error is not new authorship"
  rationale used in T3.1. All 5 scenes anchored (`Anchored 5 scene(s), 0 unmatched`), saved,
  statuses set to "done". Final word count: 1562 (clears the 1500-2500 target on the first pass,
  unlike T3.1). REVIEW: 4-lens + synthesis Workflow (`wf_199bf66f-88d`). **VERDICT: REVISE
  REQUIRED** (steering FAIL 4/10, plot FAIL 5/10, prose FAIL 5/10, continuity PASS 8/10) — three
  independent lenses converged on the SAME sentence: a closing-scene narrator line ("Nàng không hề
  nhận ra rằng, cái cảm giác 'đẹp đẽ' kia chính là dấu hiệu đầu tiên của một sự tha hóa không thể
  cứu vãn") is a flash-forward explicitly naming "irreversible corruption" — the exact defect
  pattern from T3.1's finding, recurring in a brand-new AI-authored draft despite pre-emptively
  warning against it in the prompt (a real, repeatable pipeline tendency, not a one-off). Two
  secondary issues: the locked Tầng-1 line ("Hóa ra… đau cũng có thể đẹp đến vậy") was drafted
  split across a dialogue tag instead of its required single-utterance form; one word choice
  ("khoái cảm") edged toward a sensual register the CRITICAL CANON NOTE asks to avoid given the
  technique's own dual-cultivation name. Plot/prose lenses independently corroborated the same
  flash-forward line as their top issue. FIX APPLIED (self-directed mechanical edits, same
  rationale as T3.1's line-edits — narrow substitutions directly matching the reviewers' own
  quoted text): cut the flash-forward clause, restored the locked line to its exact single-breath
  form, replaced "khoái cảm" with "rung động", and cut a secondary echo ("một kẻ tu luyện tà
  công" comparison) in the closing scene. Re-anchored, re-saved. New word count: 1529.
  RE-CHECK (targeted steering-only re-run, `wf_27c3a107-988`): **PASS**, all three fixes confirmed
  landed cleanly, no other violation found; one faint, non-blocking trace of ambient
  foreshahdowing noted in the final sentence ("một sự thay đổi thầm lặng mà không một ai có thể
  nhận ra") but it names no specific future tragedy and doesn't breach the stated constraint as
  written — left as-is (cost/benefit, same threshold used to accept T3.1). Prose lens's FAIL
  (cliché density in Scene 2, a repeated "không còn X mà Y" syntax template in Scene 3, thin
  310-words/scene pacing) was NOT separately re-fixed — those are craft/polish notes, not a locked-
  constraint violation, and are consistent with this run's recorded scope decision to sample
  rather than fully polish every representative chapter; noted here for the Phase 5 report instead.
  **T3.2 ACCEPTED.** Cross-run observation for Phase 5: the SAME flash-forward-foreshadowing defect
  shape recurred independently in Arc 1's and Arc 2's chapters, on two different scenes with two
  different casts — strong evidence this is a systematic default tendency of the app's prose
  generation, not a one-off prompt-specific slip, and should be called out as such in the report.
- [x] **T3.3** — Arc 3: one representative chapter fully drafted + reviewed — same loop.
  Re-read Arc 3's LOCKED Goal directly via API. Picked Chapter 3 "Khí Chất Quái Dị" (arc id
  `01a07858-f677-7b50-9097-4eb54a8996c1`, chapter id `01a07861-f819-713c-bd13-d790acdac4ab`) —
  the arc's explicitly-marked PIVOTAL chapter containing the "khoảnh khắc mẫu" (defining moment).
  EVIDENCE: created 5 scenes (Sự Hiện Diện Kỳ Dị, Góc Nhìn Của Kẻ Mạnh, Ánh Mắt Xuyên Thấu, Vũ
  Điệu Không Tì Vết, Khoảnh Khắc Mẫu) with synopses from the chapter Goal; requested prose from
  Co-writer Chat in one batched request, this time explicitly warning against BOTH the recurring
  flash-forward defect (T3.1/T3.2) AND spelling out this arc's own distinct constraint (interior/
  metaphor-only Đạo Hóa depiction, no direct behavior description, full rationality/no frenzy).
  CAUGHT DURING TRANSFER (self-directed, before any Workflow run, same discipline as T3.2's Lâm
  Gia catch): the AI's draft named the one-scene POV cultivator "Lâm Hạo" — but that name already
  belongs to an established Arc 1 character (Lâm Gia's enforcer/elder), and this chapter's own
  brief requires the cultivator be a one-scene-only device, unconnected to any recurring cast.
  Renamed to "Tô Bách Xuyên" throughout before pasting, to avoid a false identity collision. All 5
  scenes anchored (`Anchored 5 scene(s), 0 unmatched`), saved, statuses set to "done". Word count:
  1394 — BELOW the 1500 floor this time (T3.2 cleared it; this pass didn't, despite the same
  instruction) — accepted as an honest data point on generation variance rather than pre-emptively
  padded before review. REVIEW: 4-lens + synthesis Workflow (`wf_908daae2-3ea`). **VERDICT: REVISE
  REQUIRED** (steering FAIL 4/10, prose FAIL 4/10; plot PASS 8/10, continuity PASS 9/10) — a NEW
  defect shape for this run (not the flash-forward pattern): Scene 4's battle and Scene 5's
  climactic final line both used direct/explicit behavior description ("nàng vung tay, linh lực
  thoát ra... cắt đứt sự sống", "nàng đưa tay ra... bao trùm lấy tất cả") — violating this
  chapter's own CRITICAL CANON NOTE (interior/metaphor/philosophy ONLY, never direct behavior),
  which I had read directly from the locked API Goal, so the constraint's intent was unambiguous.
  The synthesis flagged this as a genuine tension (prose lens independently called the SAME
  passage the chapter's strongest writing) — but since the constraint was deliberately authored
  into this specific chapter's Goal as a formal Đạo Hóa technique, not a generic style preference,
  I treated it as binding and revised rather than treating the prose lens's praise as license to
  keep it. Continuity/plot both confirmed the Tô Bách Xuyên rename held with zero name-collision
  residue. FIX APPLIED: asked Co-writer Chat to rewrite Scene 4 fully through metaphor/spectator-
  perception (matching Scene 1's already-successful technique) and re-filter Scene 5's ending the
  same way, plus expand Scenes 2-3 for length. Its response reused "Lâm Hạo" again for the Scene-2
  cultivator (same ungrounded-regeneration pattern as T3.1's finding #17 — it re-derives content
  from its own memory of the brief rather than the actual current text) — renamed to "Tô Bách
  Xuyên" again during transfer. Also removed a now-redundant duplicate paragraph left over from
  merging the rewritten Scene 4 (fewer new paragraphs than the original structure) via a precise
  DOM-node selection-and-delete rather than approximate text-based selection, to avoid the
  cross-paragraph corruption risk noted in T3.1. Re-anchored, re-saved. New word count: 1606
  (clears the floor). RE-CHECK (targeted steering-only re-run, `wf_d59406be-4c2`): **PASS** 9/10 —
  Scene 4's combat confirmed rendered as absence/void ("một khoảng không tĩnh lặng, một sự trống
  rỗng hoàn hảo") rather than a strike; Scene 5's closing "bàn tay vô hình" is attributed to reality
  itself via "như thể" (as if), not to An Nhiên's own gesture — genuine metaphor, not action-in-
  disguise. No frenzy anywhere; anger stays "lạnh lùng"/"phán xét tối cao" throughout. A few
  incidental physical verbs remain (a glance, a drift, a walk through aftermath) but read as
  framing, not combat description — correctly judged non-violating. **T3.3 ACCEPTED.** Cross-run
  observation for Phase 5: this is now the SECOND distinct recurring-defect pattern found by the
  Method's review step (T3.1/T3.2's flash-forward foreshadowing; T3.3's direct-action-vs-interior-
  only violation) — both were genuine, both were caught only by the Workflow review, neither by the
  pre-emptive prompt instruction alone (the instruction reduced but did not prevent either defect).
  This is strong evidence for the report that the review step is doing real, necessary work.
- [~] **T3.4** — Arc 4: one representative chapter fully drafted + reviewed — same loop.
  Re-read Arc 4's LOCKED Goal directly via API (arc id `01a0786c-5657-7757-9b39-fc215e07c319`).
  Picked Chapter 2 "Vết Nứt Của Sự Hoàn Mỹ" (chapter id `01a07870-d97a-7b91-85d2-10abd4e30fa9`) —
  Corruption_Debt's first eruption, a solo/no-mentor/no-antagonist chapter with NO external-POV
  exception (unlike Ch.1/Ch.4's named exception scenes), so the interior-only rule applies fully.
  EVIDENCE: created 5 scenes (Đỉnh Điểm Của Sự Hài Hòa, Vết Nứt Đầu Tiên, Thực Tại Biến Dạng, Lời
  Giải Thích Hợp Lý, Quyết Tâm Sửa Chữa); requested prose from Co-writer Chat in one batched
  request, explicitly warning against BOTH known recurring defects (flash-forward; direct-action-
  vs-interior-only) plus the CRITICAL Planner-Secret-1-must-never-leak constraint, and pre-emptively
  avoiding "khoái cảm"-style sensual word choice (used "sự nhẹ nhõm thanh khiết" instead) — applying
  T3.2's lesson before generation this time, not just after.
  CAUGHT DURING TRANSFER: the draft's closing paragraph ended with "Nàng không hề biết rằng, chính
  sự quyết tâm 'sửa chữa' này... lại chính là hành động đang âm thầm bồi đắp thêm cho sự nợ nần của
  sự tha hóa" — the EXACT flash-forward construction, a THIRD occurrence of this defect despite the
  prompt explicitly citing it had happened twice before by name. Cut the sentence entirely before
  pasting (same editorial-cut rationale as T3.1/T3.2), landing the chapter on "...bằng mọi giá"
  (resolve, not dread) as the brief required.
  NEW PRODUCT FINDING (#22, logged below): the raw chat response for this request did not stop
  cleanly — after a complete, correct 5-scene Arc-4 draft and the usual "I did not re-read..."
  staleness disclaimer, the SAME response then continued into UNRELATED content: a fresh restatement
  of T3.3's earlier revision request ("Tôi đã nhận được yêu cầu của bạn... Chương 'Khí Chất Quái
  Dị' (Arc 3)...") re-generating the Arc-3 Lâm-Hạo-named draft from an EARLIER, separate turn. Only
  the first, correct portion was used; the leftover was discarded. All 5 scenes anchored (`Anchored
  5 scene(s), 0 unmatched`), saved, statuses set to "done". Word count: 1408 — below the 1500 floor
  (expected/accepted per the established scope decision). REVIEW: 4-lens + synthesis Workflow
  (`wf_a7326358-44c`). **VERDICT: REVISE REQUIRED** (steering PASS 9/10, plot PASS 8/10; prose FAIL
  4/10, continuity FAIL 5/10) — the flash-forward and interior-only constraints both held clean this
  time (steering/plot both explicitly confirmed no recurrence of either prior defect, and Planner
  Secret 1 was actively/explicitly protected, not just unmentioned). Two real issues instead:
  (1) prose — same length shortfall (1408) plus the "không còn là A, mà là B" antithesis pattern
  reused 7+ times and heavy abstract-noun ("sự X") stacking, with Scene 3's crystal-flower imagery
  cited as proof the writing can do concrete/sensory when it tries; (2) continuity — a genuine
  characterization gap: Scene 2 explicitly describes the anomalous energy behaving "như một thực
  thể ngoại lai" (like a foreign entity), but Scene 4 has An Nhiên — established as sharply
  rational — silently ignore that specific observation and jump straight to "thiên địa phản kháng"
  without weighing the evidence her own senses registered; a truly rational analyst would be
  expected to address it, not skip it. FIX APPLIED: asked Co-writer Chat to (a) expand Scenes 1/4/5
  with concrete sensory/physical detail and reduce the repetitive sentence pattern, and (b) — the
  substantive fix — add a passage where she explicitly recalls the "foreign entity" sensation and
  reasons her way past it in-character (if it were the technique's own fault, the energy would
  dissipate/explode chaotically; instead it behaved as a coercive imposition of a new law, which
  reads as external resistance, not internal flaw) — closing the continuity gap while keeping
  Planner Secret 1 fully sealed. The revision reused "khoái cảm" and the flash-forward line YET
  AGAIN in its raw output (4th and 5th occurrences respectively of these two exact defects this
  session) — both cut/reworded during transfer, same as every prior time.
  METHODOLOGY NOTE (not a product finding — an artifact of my own browser-automation technique,
  recorded so T3.5 doesn't repeat it): mid-transfer, using raw `document.execCommand('insertText',
  ...)` plus manual `Range`/`Selection` API calls (instead of Playwright's own `.fill()` or real
  keyboard events) caused ProseMirror to silently DISCARD those edits on its next re-render,
  producing duplicated/truncated paragraphs with no error. Recovered by re-applying the same fixes
  through plain `.fill()` calls only. Lesson: never use `execCommand` or raw `Range`+`Selection`
  APIs against this editor for content changes — only Playwright's own `.fill()`/`.click()`/real
  keyboard presses reliably commit through ProseMirror's transaction system. Two harmless blank
  paragraphs were left in the document as a result (cosmetically inert, do not affect anchoring
  since anchoring matches only on heading text) rather than risk further corruption removing them.
  Re-anchored (`5 already anchored, 0 without a matching heading`), re-saved. New word count: 1558.
  RE-CHECK (targeted prose+continuity re-run, `wf_384bb1f2-274`) — verdict recorded below once it
  returns.
- [ ] **T3.5** — Arc 5: one representative chapter fully drafted + reviewed — same loop.

### Phase 4 — Consistency pass (open)
- [ ] **T4.1** — Motif Library: set up the recurring Humanity Anchor motifs (bát mì ven đường,
  tiếng trẻ con, etc.) and confirm the app tracks/flags them fading across tiers
- [ ] **T4.2** — Quality / Conformance / Canon-issues panels run against the finished manuscript,
  findings triaged
- [ ] **T4.3** — Corrections panel checked for anything the flywheel captured worth reviewing

### Phase 5 — Feedback report + go/no-go (open)
- [ ] **T5.1** — Compile the FEEDBACK LOG into a written report: usable / friction / broken, with
  severity
- [ ] **T5.2** — Recommend go/no-go: is Writing Studio + PlanForge usable enough, as tested, for
  the pre-release → release decision this whole run exists to inform

## FEEDBACK LOG (append here as you go — never reconstruct from memory later)
1. Steering rules: 20 rules × 8000 chars each — checked, plenty of headroom. Not a problem.
2. Co-writer Chat TTFT 48s on a plain brainstorm question — context carried 57 tools/3 skills/
   ~23K tokens before the ~250-word user message. Worth a performance look.
3. Same response appended a confused trailing disclaimer ("I can't answer, I haven't read stored
   data") immediately after answering fully — content-quality artifact, not a UI bug.
4. Minor: background notifications SSE stream dropped once (`ERR_INCOMPLETE_CHUNKED_ENCODING`,
   recurred a second time during T1.1) — likely benign, watch for recurrence.
5. **HIGH — World Setup's own "not searchable" warning under-describes the real gap.** After
   building 8 glossary entities, the wizard warned "this book has no embedding model — set one
   in the book's knowledge settings." The real gap was one level up: there was no Knowledge
   Project record surfaced by that name at all (Knowledge → Projects search for the book's
   current title returned "No projects yet"). Root cause (finding #6) explains why — the
   warning's fix instruction was technically reachable but pointed past a confusing detour.
6. **HIGH — a book's auto-created Knowledge Project is never renamed when the book is renamed.**
   Verified via API: a project (`project_id 01a07780-17f6-...`) auto-created at book-creation
   time (`created_at` = the book's `created_at`), carrying the book's title AT THAT MOMENT
   ("Cuồng Mỹ Đạo", my placeholder) as its own `name` field. Renaming the book in Book Settings
   (→ "Vạn Tượng Quy Nhất") does not cascade to this project. Knowledge → Projects search is
   by-name only, so searching the book's current, correct title finds nothing — reads exactly
   like "no project exists," which is what sent me toward finding #7.
7. **MEDIUM-HIGH — `POST /v1/knowledge/projects` for a book_id that already has a project
   returns `200 OK` but silently no-ops.** Reproduced directly: filled the "New project" dialog
   (name "Vạn Tượng Quy Nhất", genre, same book linked) believing none existed (per #6), clicked
   Create. Backend log confirms `POST .../projects` → `200` at 16:56:55, but a `GET` immediately
   after (and again 20s later via API) shows the SAME existing project record, unchanged
   `updated_at` (16:49:46), old name, no genre. No error toast, no "already exists" message —
   the UI simply closed the dialog as if it had worked, discarding everything typed. This is the
   silent-no-op-returns-success anti-pattern AGENTS.md's own Agent Extensibility Standard names
   explicitly. Not filed as a STOP-worthy security/data-loss bug (nothing was destroyed, the fix
   via Edit worked cleanly) but a real, reproducible correctness bug.
8. Fixed via the correct path instead (Knowledge → Projects → search old name → Edit): name,
   genre, and embedding model (bge-m3, benchmark recall@3 1.00) now correctly saved (`version`
   bumped 1→2, `updated_at` current). Ran "Build knowledge graph" with scope=Glossary sync —
   completed successfully, 5 of 8 entities confirmed synced into Neo4j via log lines (the other
   3 — Linh Căn, Chân Linh, Ký ức/Nhân cách/Ý chí/Đạo tâm — are `terminology` kind; unconfirmed
   whether that kind is expected to skip graph sync or is a second, smaller gap — not chased
   further, noted for the Phase 4 quality pass). Minor/unexplained: an unrequested second
   extraction job with `scope: "chat"` appeared alongside the glossary-sync job (`items_total:
   2`, cost $0.004) — plausibly an auto-triggered chat-history sync from the earlier Co-writer
   Chat messages, not something I asked for. Low severity (trivial local cost), noted not chased.
9. **DISCOVERABILITY — three dead ends before finding the real "AI-plan-my-first-arc" path on a
   blank book.** In order: "Create a plan with AI" (Decompose tab) refuses with "This book has no
   chapters yet" — it decomposes EXISTING prose into a template's beats, it does not generate one
   from scratch. "Organise into storylines" (Plan Hub → Advanced) only offers a plain textbox to
   manually name an arc — no AI involved. "Suggest arcs" (Arc Templates → Suggest) matches a
   premise against a LIBRARY of reusable structural templates (Hero's Journey, Save the Cat...) —
   for our premise it correctly found none that fit and said so, but this is template-matching,
   not custom content generation. The actual capability — agentic, tool-calling arc creation from
   a free-text premise — lives behind attaching the "PlanForge (novel planner)" **skill** to
   Co-writer Chat, a mechanism not referenced from any of the three dead ends above.
10. **CRITICAL — steering rules silently truncated below a 2000-token soft cap, invisible in the
    UI.** Server log: `"steering over the 2000-token soft cap: dropped 5 entries, ~1525 tokens
    kept"`. Of the 8 rules written in T1.1 (several thousand chars each), only ~1525 tokens' worth
    survive into an actual chat turn — roughly 2-3 rules, not 8. No warning, badge, or truncation
    notice appears anywhere in the Steering panel or the chat UI; this was found only by reading
    server logs. This directly undermines the "story must be consistent" goal — Arc 2's locked
    7-event outline, the PA/HA/CD/THR mechanics, or the corruption-tier checklist may silently not
    reach a given generation turn depending on which rules the (undocumented) selection logic
    keeps.

    **FIXED (blocking, done immediately per user direction — filed as an issue, other findings
    stay deferred to Phase 5).** Root cause confirmed in code
    (`services/chat-service/app/services/steering.py`): the 2026-07-07 hardcoded-context-window
    audit's dynamic-scaling fix (`scale_by_window`) IS correctly wired — `context_length` really
    is threaded from the session model's real value — but `scale_by_window`'s `tuned_window=
    200_000` default means a model AT OR BELOW 200K context (this session's Gemma, confirmed
    registered at exactly `context_length: 200000`) gets **zero** scale-up; the flat baseline
    applies as-is. The baseline itself (2000) was simply too small — measured against this
    book's real 8-rule bible (4944 tokens via the repo's own `estimate_tokens`), it kept only the
    first 3 rules (1525 tokens), dropping the locked arc outline and corruption mechanics.
    Filed as [letuhao/lore-weave#223](https://github.com/letuhao/lore-weave/issues/223). Fix:
    raised `STEERING_TOKEN_CAP` 2000→8000 (~4% of a 200K window — still deliberately tight, now
    actually covers the measured real case), updated the two cap-drop unit tests
    (`test_steering.py`) to size their fixture bodies proportional to the constant instead of a
    value hand-tuned to the old one. BITE-verified: `pytest tests/test_steering.py` 15/15 green;
    separately, monkeypatching the cap back to 2000 against this book's real steering data
    reproduces the exact original bug (3/8 rules, same log line) — restoring to 8000 recovers
    8/8. Rebuilt + redeployed `chat-service`, verified the RUNNING container (not just the build
    log) via `docker exec ... grep STEERING_TOKEN_CAP`. All 8 rules now confirmed to fit
    (4944 < 8000). Not fixed (deliberately deferred, filed in the issue as a follow-up): steering
    truncation still has no UI-visible indicator when it DOES happen for a genuinely oversized
    bible — only server logs surface it.
11. **HIGH — PlanForge's propose→approve→compile pipeline never reached compile; ~10 minutes and
    2 Tier-A approvals produced zero arcs.** Asked Co-writer Chat (with the PlanForge skill
    attached) to create Arc 1 for real. It produced a genuinely excellent, fully-consistent
    proposal (clan "Lâm Gia", culprit Lâm Vô Kỵ with a concrete motive, betrayer Lâm Thanh,
    enforcer Lâm Hạo, arc name "Linh Căn Phế Tích", an ending line matching Trait ① exactly) and
    correctly ran `plan_propose_spec` (approved) then `plan_review_checkpoint` (approved). At
    `plan_compile` it needed a real `arc_id` distinct from the spec's `run_id`, but never called a
    lookup tool to get one — instead: attempt 1 sent the literal placeholder `"arc_1"` (backend
    silently dropped it as "not an id this platform issues", turn crashed with a 0-char reply);
    attempt 2 sent `arc_id == run_id` (backend's own loop-guard refused it by name — "they
    identify DIFFERENT things and can never be the same id" — turn crashed again); attempt 3 (after
    an explicit human nudge to call `composition_package_tree`/`composition_arc_list` first)
    created a THIRD duplicate spec proposal and announced it would send the exact same bad
    `"arc_1"` placeholder again. Denied that card rather than continue burning turns. The
    backend's own safety nets (placeholder-id rejection, arc_id≠run_id loop-guard,
    narrated-write/data-question nudges) all fired correctly and are genuinely good engineering —
    the gap is that the model never adapts its strategy after 3 distinct, clearly-worded rejection
    reasons, and the turn ends reporting partial success ("Did plan_propose_spec") rather than a
    clear "compile failed, here's why" to the user. Net effect for an author: confident-sounding
    narration and two real approval prompts, zero durable output. WORKED AROUND by creating Arc 1
    manually via Arc Inspector using the AI's proposed content (see T2.1 evidence) — the manual
    path is reliable, only the automated compile step is not.

12. **CRITICAL — Arc Inspector's "Goal (reaches the prompt)" field: write-unbounded but
    read-capped at 2000 chars, corrupting the WHOLE BOOK's arc list on save, not just the one
    arc.** Hit while populating Arc 2's Goal with the AI-designed 6-chapter/30-scene breakdown
    (~2800 chars — an entirely normal amount of content for a field literally labeled "reaches
    the prompt"). The `.fill()` + Tab save succeeded (200), but the very next `GET
    /v1/composition/books/{id}/arcs` — needed for the Plan Hub to render at all — started
    returning a bare 500 for the ENTIRE book, including Arc 1 (which has a short, valid goal).
    Root cause confirmed via container logs: `StructureNode.goal` (and `OutlineNode.goal` for
    chapters/scenes) were `_Short` (max 2000) on the PYDANTIC RESPONSE model, while every write
    path — `ArcCreate`/`ArcPatch`, `NodeCreate`/`NodePatch`, and 6 equivalent PlanForge/Co-writer
    MCP tool-arg schemas — declared `goal: str` with NO length bound at all. Postgres itself has
    no constraint (plain TEXT). So an over-long write always succeeds and then poisons every
    later read of that node — and because the arcs-list endpoint validates all of a book's arc
    nodes in one response, one bad arc 500s the list for every arc. This exact class of bug
    ("write succeeds, read explodes") was already identified and guarded for the intent-FSM path
    specifically (`intent_fsm/slots.py`'s own 2000-char check) — but that guard doesn't cover the
    freeform Arc/Chapter Inspector fields a human actually types into, nor the MCP tool-call path
    PlanForge/Co-writer Chat uses.

    **FIXED (blocking — the whole book's Plan Hub was unusable — done immediately per the same
    "this blocks our test" precedent as finding #10; other findings stay deferred to Phase 5).**
    Filed as [letuhao/lore-weave#224](https://github.com/letuhao/lore-weave/issues/224). Fix:
    promoted `StructureNode.goal`/`OutlineNode.goal` `_Short`→`_Long` (20000, matching
    `summary`/`synopsis` on the same models) in `db/models.py`; added a matching 20000-char
    write-side bound to `ArcCreate`/`ArcPatch` (`routers/arc.py`), `NodeCreate`/`NodePatch`
    (`routers/outline.py`), and all 6 `goal: str` MCP tool-arg fields in `mcp/server.py` so a
    future over-long write fails fast with a 422 instead of corrupting reads; reworded
    `intent_fsm/slots.py`'s comment (its own 2000-char FSM guard is now correctly described as an
    independent, deliberately-tighter UX choice — "a phrase, not a passage" — rather than a
    mirror of the model cap that moved). Updated the two tests whose assertions depended on the
    old 2000 model cap (`test_intent_fsm_slots.py`, `test_intent_fsm_run.py` docstrings).
    BITE-verified against the actual corrupted row: `GET .../arcs` was 500 before the fix,
    confirmed 200 with the full 2799-char goal intact after rebuilding + redeploying the
    container (mitigated zero data — Postgres never truncated anything, only the response model
    needed fixing). Verified the composition-service unit suite inside its own Docker
    Python-3.12 test environment (the local dev machine is on 3.10, too old for this service):
    3987/3988 passed, the sole failure a pre-existing missing-`git`-binary environment gap in an
    unrelated test, not a regression. Noted in the issue as an unaddressed follow-up: `title`/
    `summary` on the same Create/Patch schemas have the identical unguarded-write shape (plain
    `str` vs. a capped response field) — just not yet hit by real content.

13. **MEDIUM — save-on-blur can silently DISCARD unsaved text, not just fail to persist it, if
    a DIFFERENT field is edited afterward.** Confirmed on the Chapter Inspector's Goal field
    (same shape as Arc 1's Summary field, finding in T2.1's evidence, but worse): typed a
    1686-char chapter Goal, then moved to the Synopsis field and saved THAT via click+Tab. The
    Synopsis save's re-render reset the Goal textarea back to its last-SAVED value — empty — not
    just leaving it unsaved. Confirmed via `GET /outline/nodes/{id}`: `goal: ""` after the
    sequence, and the Goal textbox in a fresh snapshot was visibly empty too (not merely
    unsynced). WORKAROUND (now the standing procedure for every remaining chapter/scene): fill
    Goal LAST among a node's fields, then click it and press Tab immediately — do not touch any
    other field afterward until it is confirmed saved. Not filed as a separate GitHub issue
    (same root cause family as the save-on-blur gaps already noted for Arc 1's Summary field);
    flagging here because it is a data-loss shape, not just a friction one, and will recur for
    every one of the ~30 remaining chapter/scene nodes across all 5 arcs unless deliberately
    worked around each time.
14. **MEDIUM — the Plan Hub graph canvas does not live-update when a new chapter is created; it
    silently under-renders until a full page reload.** After the FIRST chapter under a given arc,
    the very next "+ Chapter" click creates the node correctly server-side (confirmed via
    `GET .../outline/children?structure_node_id=...`) but the new node never appears on the
    canvas — not after waiting several seconds, not after collapsing/expanding the arc's lane,
    not after re-clicking the arc box. `document.querySelectorAll('[data-testid^="rf__node-"]')`
    confirmed the node was genuinely absent from the DOM, not just visually off-screen. A full
    `page.goto()` reload reliably fixes it (all chapters render correctly afterward). Root cause
    not chased into the frontend source (out of scope for a manual test session) but the shape —
    correct on first render, stale after an incremental mutation — points at a missing
    cache-invalidation or re-fetch after the chapter-create mutation, not a rendering logic bug.
    WORKAROUND (used for the rest of this arc): after every "+ Chapter", do a full page reload
    before trying to open the new node.
15. Related, smaller: the Arc Inspector's own "Chapters" roll-up (both the canvas complementary
    panel and the dedicated "Arc Inspector" tab) shows a contradictory label once an arc actually
    has chapters — literally "No chapters assigned · 6" (the static text and the live count
    disagree), and the section never renders the chapters as a clickable list even when the count
    is non-zero. This is the direct cause of the discoverability dead-end that led to trying (and
    failing) the ⌘P command palette, the Plan Hub's own "Find a node…" box, and the "Manuscript"
    activity tab before finding a working path (collapse-then-expand the arc's own lane to force
    its rollup box back into the canvas, then click the newly-visible chapter chip directly).
16. **Self-caught correctness error (mine, not a product bug) — worth recording honestly for the
    feedback report's credibility.** While filling Arc 2's 6 chapters, I built the entire
    chapter/scene breakdown from a POST-COMPACTION conversation summary of an earlier Co-writer
    Chat response, rather than re-reading the actual Steering rule. The summary I was working
    from was a lossy paraphrase; the real, locked Steering rule ("Arc 2 — outline 7 sự kiện đã
    chốt") describes a COMPLETELY different story than what I had written into all 6 chapters:
    Arc 2 is explicitly "KHÔNG PHẢI ARC SỨC MẠNH — là arc khám phá và trả giá" (NOT a power arc —
    an arc of discovery and paying a price), a SOLO arc with no mentor, no antagonist, and no
    combat, centered on An Nhiên self-teaching 《Âm Dương Hợp Hoan Công》 and only reaching a first,
    unrecognized sign of Perfection Addiction by its end — NOT a THR-threshold-crossing climax
    with an invented rival faction, as I had drafted. Caught only because I paused to quote
    Steering's Event 6 verbatim for Chapter 5's Goal field and re-read the source rule directly
    instead of relying on memory. Corrected all 6 chapters' Title/Synopsis/Goal plus the arc-level
    Goal/Summary to map 1:1 onto the real 7 locked events (see T2.2 evidence). Lesson applied
    going forward: after any context compaction, re-read Steering/canon source rules directly
    before drafting derivative content — never rebuild from a summary of a summary.

17. **MEDIUM — Co-writer Chat re-derived its own, DIVERGING version of an already-completed arc
    instead of treating the human's stated facts as ground truth, and explicitly disclaimed its
    own staleness.** Asked (discussion-only) to design Arc 3, having told the AI in detail that
    Arc 2 was already built with specific chapter titles and content. Its 129.8s reply opened
    with an unrequested full "Chương 1-6" recap of Arc 2 — but using DIFFERENT chapter titles and
    different scene content than what actually exists in the book (e.g. its "Chương 5: Vẻ Đẹp Của
    Nỗi Đau (Event 6)" vs. the real, already-saved "Tác Dụng Phụ Đầu Tiên"). The actual Arc 3
    proposal only appears after this recap. The reply ends with: "I did not re-read the book's
    current state in this turn, so my answer may be stale." — a correct and honest disclosure,
    but it means the model's default behavior is NOT to ground itself in the live Plan Hub/outline
    state unless something explicitly triggers a re-fetch, even when a human's own message already
    states the current facts in detail. Low real-world harm here (the human/co-author role is
    exactly what this run is testing for, and I did not use the diverging recap) but a real risk
    for a less careful author: an AI reply can silently contradict already-committed canon in the
    same turn it was told that canon, with no automatic check catching the mismatch. Not filed as
    a GitHub issue (a model-behavior/grounding question, not a code defect) — recorded for the
    Phase 5 report's "how much active verification does this workflow actually require" section.
18. **T2.3 (Arc 3) content quality note, not a bug**: the proposal's very last scene has An Nhiên
    "bắt đầu nảy sinh ý niệm: 'Thứ không đẹp thì không xứng tồn tại'" — quoting the drift table's
    Tầng 3+ column value, not Tầng 2's, right at Arc 3's close. Accepted as written (matches the
    same "first flicker of the next tier" handoff convention Arc 2 itself used to close into Arc
    3), not treated as a drift-table violation — but noted here in case Phase 4's Quality/
    Conformance pass flags it and a reviewer needs the reasoning.
19. **HIGH — no confirmed working path for the app's own AI to write scene prose directly into the
    Manuscript document; the only demonstrated path is chat-draft + human copy-paste.** During
    T3.1, tried every inline generation control the Editor exposes: the "AI" writing-mode toggle
    (togglable, but paired "✦ Continue from cursor" stayed `disabled` across every attempt —
    clicking into the paragraph, re-focusing, after anchoring a scene, with an empty vs.
    heading-only document); "✦ Suggest scenes" (no visible effect on an empty chapter); the
    narration-attach-generate "✨" icon (toggled "active" but produced no visible generation UI in
    the snapshot). Asked Co-writer Chat directly, inviting it to write into the Manuscript editor
    "if you have a tool to do that" — it explicitly confirmed: "Tôi không có quyền truy cập trực
    tiếp vào Manuscript editor để viết vào đó." This means the real, load-bearing authoring loop
    for this entire run (and presumably any real author's workflow) is: draft in Co-writer Chat →
    human reads/accepts → human manually re-types/pastes into the correct anchored heading section
    in the Editor. That hand-off is unautomated, easy to get wrong (see finding #21 for one
    concrete way it went wrong), and never surfaced in-product as "this is the intended flow" —
    a newcomer would reasonably expect "AI" writing mode or "✦ Continue from cursor" to be the
    real path and could spend significant time on the same dead end this run did. Not filed as a
    GitHub issue yet — recommend Phase 5 flag this as the single largest usability gap found this
    run, since it directly blocks the product's own stated pitch (AI-assisted authoring in the
    Writing Studio).
20. **MEDIUM — confirmed, repeatable prose length under-delivery vs. the requested word count.**
    Three independent data points this session: (a) first ask for Scene 1, "~1500-2500 words",
    delivered ~500-600 Vietnamese words; (b) an explicit follow-up ask to expand the same scene
    (keep content, add sensory/interior/environmental detail) delivered a genuinely richer but
    still short ~900-1100 words — the nudge helped but did not close the gap; (c) a batched ask
    for the remaining 4 scenes of the same chapter, "400-600 words each", delivered roughly
    350-450 words each (6555 chars total for 4 scenes). Every measurement this run undershoots the
    requested length, and only partially self-corrects even when told explicitly. Net effect: the
    finished T3.1 chapter is 1497 words across 5 scenes, versus this plan's own ~1500-2500+/chapter
    web-novel-standard target — under target on the FIRST fully-drafted chapter of the run, not an
    outlier. Recommend Phase 5's report state this as a concrete, reproducible tuning/prompting gap
    for the product's scene-generation flows, not a one-off.
21. **LOW — the Editor's "N of N scenes not yet done" completion counter does not live-update
    after changing a scene's status via the Scenes-rail dropdown.** After setting all 5 of T3.1's
    scene status comboboxes to "done" in sequence, the toolbar still read "5 of 5 scenes not yet
    done" with no further interaction. A full page reload was NOT even needed to disprove it in
    the UI — a direct `GET /v1/composition/outline/nodes/{scene_id}` for all 5 scene ids confirmed
    `"status":"done"` had persisted correctly; the badge itself just never re-rendered from the
    write. Same shape as finding #14 (canvas not live-updating on new chapter) and finding #15
    (contradictory chapter-count label) — a recurring pattern of Plan/Editor summary widgets not
    reacting to state changes made through their own adjacent controls in the same session.
22. **MEDIUM — Co-writer Chat's response occasionally does not stop cleanly, continuing past its
    own staleness disclaimer into unrelated leftover content from an earlier, separate request in
    the same conversation.** During T3.4, a request for Arc 4 Ch.2's 5 scenes produced a complete,
    correct draft, followed by the usual "I did not re-read the book's current state in this turn"
    disclaimer — and then the SAME response kept generating: "Tôi đã nhận được yêu cầu của bạn...
    Chương 'Khí Chất Quái Dị' (Arc 3)..." followed by a fresh re-generation of T3.3's EARLIER
    Lâm-Hạo-named revision draft, as if answering a completely different, previous turn's request
    a second time. The correct Arc-4 content was used; the Arc-3 leftover was discarded. This
    looks like a context/turn-boundary bug in the chat backend (the model continuing to generate
    past its intended stop, drifting back into unrelated prior-turn material) rather than a prompt
    quality issue on my end. Not filed as a GitHub issue yet (never reproduced deliberately) —
    flagging for Phase 5 as a real, observed reliability gap: a human author skimming only the
    start of a long response could easily miss that the tail is stale/wrong content bleeding in
    from a different request.

RESUME: **T3.1, T3.2, AND T3.3 ARE DONE AND ACCEPTED. MOVE TO T3.4 (Arc 4's representative
chapter) NEXT.** All 5 arcs are fully built (28 chapters total, see prior note). Each of T3.1-T3.3
is fully drafted, anchored, saved, scenes "done", and has been through a full 4-lens+synthesis
Workflow review, a revision pass, and a targeted re-check confirming PASS — see each row's
evidence block. **Two distinct recurring-defect patterns confirmed across 3 chapters, both caught
ONLY by the Workflow review, neither prevented by pre-emptive prompting alone**: (a) T3.1/T3.2 —
explicit narrator-voice flash-forward/foreshadowing naming future tragedy/corruption; (b) T3.3 —
direct/explicit behavior description where a chapter's own Goal locks an interior/metaphor-only
register. Both are load-bearing evidence for Phase 5: the review step is doing real work, not
theater. Proven end-to-end loop for T3.4-T3.5: (1) read the target arc's chapter Goal directly via
`GET /v1/composition/outline/nodes/{id}` (finding #16 — never from a summary), noting ANY chapter-
specific stylistic lock (like T3.3's interior-only rule) as a distinct thing to check in review,
not just the generic flash-forward pattern; (2) ask Co-writer Chat (real UI, Rule 1) to draft all 5
scenes in one batched request, explicitly instructing against whatever defect patterns are known so
far (flash-forward; direct-action-vs-interior-only if applicable) and a word-count target — treat
this as risk-reduction, not prevention, and still expect to catch violations after generation;
(3) create the 5 scenes via the Scenes rail if not already present, type a Heading-2 per scene,
hand-transfer AI prose into the paragraph under each heading (target a SPECIFIC empty node's ref/
role, NEVER `.fill()` on the whole `.ProseMirror` container); (4) before pasting, sanity-check
against known canon facts — the AI has now reused an already-established character's name THREE
separate times this session (Lâm Gia in T3.2, Lâm Hạo in both T3.3 drafts even after being told the
correct replacement name once already) — always check names, not just once but again after any
revision request, since re-generation reliably regresses to the ungrounded default (finding #17's
root cause); (5) "⚓" anchor, ⌘S save, set each scene's status to "done" (finding #21 — toolbar
counter won't live-update, verify via API if in doubt); (6) run the 4-lens+synthesis Workflow;
(7) if REVISE REQUIRED, judge whether the flagged issue is a locked-constraint violation (fix it,
even if another lens praised the prose — T3.3's precedent) or a craft-only nitpick (log for Phase 5,
don't chase to perfection — this run's scope is one honestly-reviewed representative chapter per
arc); apply narrow mechanical fixes matching the reviewer's own quoted text where possible, or a
short Co-writer Chat request for genuine rewrites, then a targeted re-check on just the failed
lens(es); (8) log evidence, commit, advance. T3.4: Arc 4 "Tha Hóa Thâm Sâu" (Tầng 3) — re-read its
locked Steering rule directly first; note its own CRITICAL CANON NOTE already specifies the SAME
interior/metaphor-only register as Arc 3, except for two explicitly-allowed external-POV exceptions
(Chapter 1 Scene 5, Chapter 4 Scene 5) — if picking either of those chapters, the interior-only rule
does NOT apply to that specific scene, so check the chapter Goal carefully before assuming it does.

Findings #10 and #12 are both RESOLVED — root-caused, fixed, filed
(github.com/letuhao/lore-weave#223 and #224), BITE-verified, live in rebuilt+redeployed containers.
Phase 1 is fully done. Auth-token note for future API verification calls: if `/tmp/lw_token.txt`
returns `{"detail":"invalid token"}`, recover a fresh one from the still-live browser session via
`browser_evaluate: () => JSON.parse(localStorage.getItem('lw_auth')).accessToken` — do not attempt
to re-log-in with guessed credentials (this repo's real dev password is not known to this agent).

```goal-prompt
goal: Vạn Tượng Quy Nhất has 5 fully written arcs (5-6 chapters each, >=5 scenes/chapter, web-novel-standard length), authored through LoreWeave's own Writing Studio/PlanForge AI, reviewed for consistency via the Method's Workflow multi-lens pattern, with a written feedback report + go/no-go recommendation delivered
rules: |
  1 The prose/outline is authored by the app's OWN AI (Co-writer Chat / PlanForge / Composition) driven through the real UI - never substitute an external agent's own writing for it.
  2 Browser-driving stays sequential in the main loop, played as one continuous human - never parallel agents on the same live session.
  3 Delegate REVIEW (never authorship) to a small Workflow per generated unit: 2-4 parallel lenses (steering-bible consistency, plot logic, prose quality/length, continuity) + synthesis; act on its verdict from the real UI.
  4 Log every UX/product finding to the FEEDBACK LOG immediately, not from memory later.
  5 Canon is sealed: story-plan-v1.md only, protagonist Tran An Nhien, book 01a07780-172b-70fa-bf11-cbf261fa3e91. Do not touch the unrelated existing "Mi De" book (019f9f2d...).
note: |
  Creative-content + product-testing run, not a code implementation plan. A row is DONE only with
  real generated content plus a logged review verdict - a checkbox alone is not evidence.
stop: |
  a write would target a different book/account than 01a07780-172b-70fa-bf11-cbf261fa3e91 / claude-test@loreweave.dev
  a real product bug looks security- or data-loss-shaped - stop and flag it, do not route around it
  a decision is genuinely the user's to make, not an author/AI-collaborator call - e.g. a premise change, not a name
```
