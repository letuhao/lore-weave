# My first day on LoreWeave — writing my first book

*A first-run diary by an excited newcomer who signed up after seeing the ads.
Written **live** while actually clicking through the real product (baked prod build on
`:5174`, driven in a browser). Praise where it's earned, complaints where I hit walls.
Times are wall-clock from the session.*

**What I set out to do:** the ad said "draft chapters with an AI co-writer," so I came to
write Chapter One of my book — *The Lantern of Ell Marren* — and see the AI help.

**Did I get there?** Yes, eventually. I have a saved chapter and the AI gave me a genuinely
great line. But the path from "New Book" to "words on the page" made me work for it, and twice
I thought the app was broken when it wasn't. A first-timer without my patience would have bounced.

---

## TL;DR for the team

- 🎉 **The payoff is real.** The editor is lovely and the AI co-writer gave me an eerie,
  on-brief two-sentence answer in ~4 seconds for **$0** (local model). *This* is the product.
- 😖 **Getting to the payoff is a maze.** To write my first chapter I clicked **Editor**
  (dead end), **Act** (made a thing I didn't understand), gave up, found **"Plan this book,"**
  landed in a **"Plan Hub"** full of *arc / spec / extract / Unassigned* jargon, and only then
  found a friendly **"＋ Write a new chapter"** button — which was hiding behind a mode toggle
  that defaulted to the *hard* mode.
- 🐞 **Two moments made me think it was broken:** (1) the whole app looked logged-in but every
  backend call was silently failing on first paint; (2) I wrote and saved a chapter and the
  sidebar kept insisting I had **0 chapters** until I manually hit Reload.
- 🏷️ **My first chapter is named `editor-2d0fc71f-104b-4467-8555-7f9ed27f21d7.txt`.** I did not
  name it that. Nobody would.

---

## 🟢 What made me excited (please keep this)

1. **The onboarding fork is inviting.** Landing on "What do you want to do?" with five plain-English
   doors (Write / Build a world / Translate / Explore / Work assistant) is a great first screen. It
   respected that I might not be a novelist.
2. **New Book is a 10-second job.** Clean modal, "Create" stays disabled until I type a title, and it
   dropped me *straight into the Studio*. No dead "book created, now what" screen. 👍
3. **The Studio Welcome panel is thoughtful** — a real intro, a **User Guide**, a **Guided Tour**, and
   one-click **Co-writer Chat** / **Editor** shortcuts. Somebody cared about first-run here.
4. **Simple mode of the planner is exactly right for me.** *"Your book, chapter by chapter… A blank
   book. Start with a sentence — the structure can come later."* + a big **＋ Write a new chapter**
   ("Opens a blank page straight away") + a colour legend (you wrote it / AI idea / done / drafting /
   not started). If I'd *started* here I'd have zero complaints. (See the big gripe below: I didn't.)
5. **The editor is genuinely nice.** Full formatting toolbar, `/` slash-commands, live word count,
   Draft→Publish, and a rail of power tools (Grammar, Heatmap, Glossary, Focus, Scenes, Reader,
   Translate, Revision history). It felt like a real writing tool, not a form.
6. **Save is trustworthy.** Saved in a blink, and after a **full page reload my prose came back
   verbatim from the server.** That's the thing I most need to believe, and I believe it.
7. **The AI co-writer delivered the magic.** I asked it to hint at what "the water whispering her
   name" foreshadows; it answered:
   > *"The rhythmic, sibilant murmurs from the tide suggest that the Ell Marren lighthouse is not
   > merely a beacon for sailors, but a vessel for something ancient and hungry…"*
   Atmospheric, on-brief, ~4.1s, and **$0** on the local model. The persona picker (Novelist /
   Editor / Worldbuilder…) and the model chip up front are a nice touch.

---

## 🔴 What made me want to close the tab (please fix)

### 1. On first paint, the app looked logged-in but every backend call failed. `[BLOCKER-feel]`
The very first thing that happened: the sidebar cheerfully showed my name and avatar, while the
network quietly threw a wall of failures — `/v1/me/preferences`, `/v1/account/profile`,
`/v1/notifications/unread-count`, `/v1/notifications/stream`, `/v1/auth/refresh`. First it was
`ERR_CONNECTION_REFUSED` (backend still booting), then after a reload it flipped to **401 / 500**
(my cached session had expired). It self-healed via a token refresh a moment later — but for ~10
seconds I was looking at a UI that said "you're fine" while nothing worked.
**The complaint isn't that a token expired — it's that the UI lied about it.** A brand-new user in
this state has no idea whether to wait, reload, or leave. Show a tiny "reconnecting…" state instead
of rendering a confident, broken shell.

### 2. I wanted to *write*, and the app made me learn its filing system first. `[HIGH]`
My mental model was "New Book → type Chapter One." What actually happened:
- I clicked **Editor** (the obvious "write" button). It said *"Select a chapter in the manuscript
  navigator to edit it here."* — but I had **no chapters, and the editor offered no way to make one.**
  A dead end on the one screen named after writing.
- Back in the sidebar, the only create button was **"Act."** I'm a newcomer — "Act" is theatre
  jargon, and I only *wanted* a chapter. I made one anyway; it produced an "ACT" row that said
  *"drag chapters here"*… but there was **no "+ Chapter" button anywhere to drag from.**
- The Manuscript rail — the default view — literally **cannot create a chapter.** You have to know
  to leave it.

**Fix:** put a plain **"+ New chapter"** (→ opens the editor on a fresh chapter) right in the
Manuscript rail and in the empty Editor state. "Act" should read "Part / Act" and be clearly optional.

### 3. "Act" (manuscript) and "Arc" (plan) are two different structure systems, and they don't talk. `[HIGH / confusing]`
After I made an **Act** called "Part One," I went to **Plan this book** and it told me
*"No plan for this book yet… This book has none yet."* So the structural thing I just created
**doesn't exist** as far as the planner is concerned. Two parallel hierarchies — *Acts/Parts* in the
manuscript vs *Arcs* in the Plan Hub — with near-identical names ("Act" vs "Arc"!) and no visible
bridge between them. As a first-timer I could not tell you which one is "the real outline."
**Fix:** one spine, or at minimum make the naming and the relationship explicit ("Acts group your
manuscript; Arcs are the plan — here's how they line up").

### 4. The friendly door defaults to the intimidating room. `[HIGH]`
The single best newcomer surface — Plan Hub **Simple** mode — was **not** what opened. The planner
came up in **Advanced** (a canvas that talks about *spec, extract, scenes, Unassigned strip*). Simple
mode was one toggle away, but I only found it by poking. A first-time writer should land in Simple by
default and *graduate* to Advanced.
*(Caveat: this is the shared test account, so a per-user preference may have been left on Advanced by
earlier testing. Worth confirming the true default for a genuinely new account — but even so, the
maze in #2 means most newcomers never reach this toggle at all.)*

### 5. I saved a chapter and the sidebar kept saying I had **0 chapters**. `[HIGH — looks like data loss]`
After **＋ Write a new chapter** → typing → **Save** ("saved" ✓, footer showed *43 words*), the
Manuscript rail **still read "1 act · 0 ch"** with no chapter row. It only appeared after I manually
clicked **Reload** ("1 act · 1 ch"). To a newcomer, "I saved and it says I have nothing" reads as
**lost work** — the single scariest thing a writing app can imply. The data was safe (it survived a
full reload), but the sidebar didn't refresh itself.
**Fix:** invalidate/refresh the manuscript tree when a chapter is created (this smells like a
hand-rolled navigator that a query invalidation doesn't reach).

### 6. My first chapter was auto-named `editor-2d0fc71f-104b-4467-8555-7f9ed27f21d7.txt`. `[MEDIUM — but very visible]`
That raw internal filename/UUID is what shows in the sidebar as my chapter's **title**, and it
**persists on the server** (survived reload). It also silently filed under **"Unassigned"** rather
than the Act I'd just made. First impressions: my beautiful opening scene is labelled like a temp
file. **Fix:** default new chapters to "Chapter 1" / "Untitled chapter" and let me rename; never
surface the storage filename as the display title.

### 7. Small stuff that adds up `[LOW / polish]`
- The tab bar reads **Manuscript / plan / Story Bible / Search / Quality** — **"plan" is lowercase**
  while every sibling is Title Case.
- The notifications badge shouts **"99+"** at what feels like a brand-new account. Alarming for a
  first-timer (even if it's inherited test data, a real new user should start at 0).
- **Cost of a throwaway question:** my two-sentence creative ask sent **≈22,600 input tokens** (the
  co-writer preloaded "48 tools · 5 skills · ~12,900 tok" of context). Invisible & free on the local
  model — but on a paid BYOK model, a newcomer idly chatting would burn real money without realising
  a trivial question isn't trivial under the hood. Consider a lighter context for plain creative chat.

---

## The journey, step by step (what I actually clicked)

| # | I did… | I got… | Verdict |
|---|--------|--------|---------|
| 1 | Opened the app | `/onboarding`, 5 clear doors, **but 6 failed backend calls on first paint** | 🎉 screen / 😖 errors |
| 2 | (auth self-healed) → **Workspace** | "My Books," one stray test book, **99+** notif badge | ok |
| 3 | **New Book** → titled it, picked English | clean modal, dropped into the **Studio** | 🎉 |
| 4 | Clicked **Editor** to write | *"Select a chapter…"* — but none exist, no way to make one | 😖 dead end |
| 5 | Clicked **Act** (only create button) | an "ACT" row saying *"drag chapters here"* — nothing to drag | 😖 jargon |
| 6 | Clicked **Plan this book** | **Plan Hub**, *"No plan yet"* — my Act didn't register here | 😖 two systems |
| 7 | Toggled **Simple** mode | the friendly *"＋ Write a new chapter"* screen I'd wanted all along | 🎉 (buried) |
| 8 | **＋ Write a new chapter** | a real, rich editor opened | 🎉 |
| 9 | Typed my opening lines → **Save** | "saved" ✓, 43 words — **but sidebar still said 0 chapters** | 😖 looks lost |
| 10 | Manual **Reload** | chapter appears — titled `editor-<uuid>.txt`, under "Unassigned" | 🐞 ugly name |
| 11 | **Co-writer Chat** → Novelist → asked for foreshadowing | eerie, on-brief 2 sentences, ~4.1s, **$0** | 🎉🎉 |
| 12 | Full page **reload** | 0 console errors, chapter + prose restored from server | 🎉 durable |

---

## If you fix five things before the next newcomer arrives

1. **Never render a confident logged-in shell while auth is failing** — show "reconnecting…". *(#1)*
2. **Let me create a chapter from the Manuscript rail and the empty Editor** — a plain "+ New
   chapter" that opens the editor. Don't force the Plan Hub detour. *(#2)*
3. **Auto-refresh the manuscript tree when a chapter is created** — "saved but 0 chapters" reads as
   data loss. *(#5)*
4. **Give new chapters a human title** ("Chapter 1"/"Untitled"), never the storage filename. *(#6)*
5. **Default first-timers into Plan Hub *Simple* mode**, and reconcile the **Act vs Arc** double
   hierarchy (or at least name it so a human can tell which is "the outline"). *(#3, #4)*

Do those and the maze becomes a hallway — and the payoff (that editor, that co-writer) is already
good enough to make me stay.

*— filed by the new kid, having successfully written, saved, and AI-augmented Chapter One of*
*"The Lantern of Ell Marren." Book id `019f73f2-04bf-777b-8609-6207ec8450aa` if you want to look.*
