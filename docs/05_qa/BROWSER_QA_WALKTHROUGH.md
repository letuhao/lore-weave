# LoreWeave — Browser QA Walkthrough

> **Purpose:** A step-by-step script for a browser agent (or human tester) to play as a writer using LoreWeave. Covers all major screens and realistic workflows.
>
> **How to use:** Follow each scenario in order. Each step has an **Action** (what to do) and a **Verify** (what to check). Take screenshots at each verify point. Record any bugs, UI issues, or unexpected behavior.
>
> **Environment:** `http://localhost:5174` with all Docker services running.
> **Test account:** `letuhao1994@gmail.com` / `Ab.0914113903`

---

## Pre-flight Checklist

- [ ] Docker Compose is running (`docker compose up -d`)
- [ ] Frontend is accessible at `http://localhost:5174`
- [ ] LM Studio is running with a model loaded (for AI features)
- [ ] Browser: Chrome (for Web Speech API support)

---

## Scenario 1: First Look — Navigate All Screens

**Goal:** Visit every major screen and verify it loads without errors.

### 1.1 Login
- **Action:** Navigate to `http://localhost:5174`. Enter test credentials and click "Sign In".
- **Verify:** Redirects to `/books`. Sidebar shows: Workspace, Chat, Browse, Trash, Usage, Leaderboard, Settings. User name appears at bottom.

### 1.2 Sidebar Navigation
- **Action:** Click each sidebar item in order.
- **Verify:**
  - Workspace (`/books`) — Shows book list with at least 1 book
  - Chat (`/chat`) — Shows conversation list, "New" button
  - Browse (`/browse`) — Shows public book catalog
  - Trash (`/trash`) — Shows empty or trashed items
  - Usage (`/usage`) — Shows usage stats/billing
  - Leaderboard (`/leaderboard`) — Shows ranking tabs
  - Settings (`/settings/account`) — Shows account settings with tabs

### 1.3 Settings Tabs
- **Action:** Click through each settings tab: Account, Model Providers, Translation, Reading, Language.
- **Verify:** Each tab loads without error. Model Providers shows configured AI models.

---

## Scenario 2: Create a New Book

**Goal:** Create a book, add a chapter, write content.

### 2.1 Create Book
- **Action:** Go to Workspace. Click "New Book". Fill in:
  - Title: "QA Test Novel"
  - Language: "zh" (Chinese)
  - Description: "A test novel for QA walkthrough"
- **Verify:** Book appears in the list. Click it to open Book Detail page.

### 2.2 Book Detail — Tabs Overview
- **Action:** On the Book Detail page, click each tab header.
- **Verify:** All tabs load:
  - Chapters — shows "0 chapters" with Import + New Chapter buttons
  - Translation — shows empty translation matrix
  - Glossary — shows "0 entities" with Extract, Genres, Kinds, New Entity buttons
  - Wiki — shows empty wiki
  - Sharing — shows visibility settings
  - Settings — shows book settings (genre tags, etc.)

### 2.3 Create a Chapter
- **Action:** On Chapters tab, click "New Chapter". Fill in:
  - Title: "第一章 黎明前的黑暗"
  - Language: "zh"
  - Body: Paste 500+ characters of Chinese text (novel-style prose with character names, locations, dialogue)
- **Verify:** Chapter appears in the list with title, language, status "Active".

### 2.4 Edit the Chapter
- **Action:** Click the pencil icon on the chapter row to open the editor.
- **Verify:** Tiptap editor loads with the chapter content. Format toolbar visible. Slash menu works (type "/").

### 2.5 Add Rich Content
- **Action:** In the editor:
  1. Add a heading (select text → H2 in toolbar)
  2. Add a blockquote (select text → quote in toolbar)
  3. Add bold and italic formatting
  4. Type "/" and select "Image" from slash menu — upload a test image
  5. Save (Ctrl+S or save button)
- **Verify:** All formatting renders correctly. Image appears inline. Save succeeds (no error toast).

---

## Scenario 3: Glossary Extraction (AI-Powered)

**Goal:** Use the GEP wizard to extract characters and locations from the chapter.

### 3.1 Open Extraction Wizard from Chapters Tab
- **Action:** On the Chapters tab, click the sparkle (✨) icon on the chapter row.
- **Verify:** Extraction wizard opens in **single mode** (no Chapters step). Step indicator: Profile → Confirm → Progress → Results.

### 3.2 Configure Extraction Profile
- **Action:**
  1. Select an AI model from the Model dropdown (e.g., Qwen 3.5 or any available model)
  2. Verify Character kind is pre-checked with attributes (name, aliases, gender, etc.)
  3. Verify Location kind is pre-checked
  4. Expand Character kind (click chevron) — see all attribute dropdowns
  5. Change "occupation" from "Fill missing" to "Skip"
  6. Click "All Overwrite" on Location kind
  7. Click "Next"
- **Verify:** Step advances to Confirm. Profile summary shows selected kinds with attribute counts.

### 3.3 Confirm and Start Extraction
- **Action:** On Confirm step:
  1. Verify summary shows: 1 chapter, correct kind count, model name
  2. Click "Start Extraction"
- **Verify:** Step advances to Progress. Progress bar appears. "Processing chapter 1 of 1..." shown.

### 3.4 Monitor Progress
- **Action:** Wait for extraction to complete (30-120 seconds depending on model).
- **Verify:**
  - Progress bar fills to 100%
  - Stats show entities found/created/updated/skipped
  - Activity log shows chapter completion
  - Step auto-advances to Results

### 3.5 Review Results
- **Action:** On Results step:
  1. Check summary stats (created, updated, skipped, failed)
  2. Check token usage
  3. Click "Review in Glossary"
- **Verify:** Wizard closes. Glossary tab shows newly extracted entities with kind badges (Character, Location, etc.).

### 3.6 Verify Extracted Entities
- **Action:** On Glossary tab:
  1. Click on a Character entity to open the Entity Editor
  2. Check attribute values (name, aliases, gender, appearance, etc.)
  3. Check evidence tab — should show extracted quote from the chapter
  4. Check chapter links — should show the chapter we extracted from
  5. Close the editor
- **Verify:** Entity has populated attributes in Chinese (the source language). Evidence quotes are from the chapter text.

---

## Scenario 4: Batch Extraction from Glossary Tab

**Goal:** Test batch extraction with multiple chapters.

### 4.1 Create More Chapters
- **Action:** Go to Chapters tab. Create 2 more chapters with Chinese content:
  - "第二章 觉醒" (500+ chars)
  - "第三章 对决" (500+ chars)
- **Verify:** 3 chapters total in the list.

### 4.2 Batch Extract from Glossary Tab
- **Action:** Go to Glossary tab. Click "Extract" button in the toolbar.
- **Verify:** Wizard opens in **batch mode**. Step indicator: Profile → Chapters → Confirm → Progress → Results.

### 4.3 Configure Batch
- **Action:**
  1. On Profile step: select model, verify kinds, click Next
  2. On Chapters step: verify "All chapters" is selected (3 chapters)
  3. Try "Pick chapters" mode — deselect one chapter, re-select it
  4. Adjust silence threshold slider
  5. Click Next
- **Verify:** Confirm step shows 3 chapters, correct kind count, estimated LLM calls.

### 4.4 Run Batch Extraction
- **Action:** Click "Start Extraction". Wait for all 3 chapters to process.
- **Verify:**
  - Progress shows chapters completing sequentially
  - Entity count increases with each chapter
  - "updated" count increases (entities seen across chapters)
  - Results show per-chapter breakdown

---

## Scenario 5: Translate the Glossary

**Goal:** Translate entity names and attributes into another language.

### 5.1 Open Entity Editor
- **Action:** On Glossary tab, click on the main character entity.
- **Verify:** Entity Editor opens with all attributes.

### 5.2 Add Translation
- **Action:**
  1. Find the "name" attribute
  2. Click "Add Translation" or the translation icon
  3. Select language: "en" (English)
  4. Type the English translation of the character name
  5. Set confidence: "verified"
  6. Save
- **Verify:** Translation appears under the attribute value. Language tag "en" visible.

### 5.3 Translate Multiple Attributes
- **Action:** Add English translations for: aliases, role, description.
- **Verify:** Each translation saves successfully. Translation count updates on the entity row in the list.

---

## Scenario 6: Translate a Chapter

**Goal:** Use the translation pipeline to translate a chapter from Chinese to English.

### 6.1 Open Translation Tab
- **Action:** Go to Translation tab on the book detail page.
- **Verify:** Translation matrix shows 3 chapters. If no translations exist, all cells show "—".

### 6.2 Start Translation
- **Action:**
  1. Select checkbox on chapter 1
  2. FloatingActionBar appears: "1 chapter selected"
  3. Click "Translate Selected"
  4. In TranslateModal: select target language "en" (English)
  5. Select AI model
  6. Click "Start Translation"
- **Verify:** Toast confirms translation job started. Matrix cell changes to "Running" or spinner.

### 6.3 Wait for Translation
- **Action:** Wait for translation to complete (60-180 seconds).
- **Verify:** Matrix cell changes to "✓ Done" (green).

### 6.4 View Translation
- **Action:** Click on the "✓ Done" cell to view the translation.
- **Verify:** Chapter translations page opens. Shows source text and translated text side by side (or in version list).

---

## Scenario 7: Publish and Browse

**Goal:** Make the book public and browse it as a reader.

### 7.1 Set Visibility to Public
- **Action:** Go to Sharing tab. Change visibility to "Public".
- **Verify:** Visibility badge changes to "Public" in the header.

### 7.2 Browse Public Catalog
- **Action:** Go to Browse (`/browse`) in the sidebar.
- **Verify:** "QA Test Novel" appears in the catalog. Cover/title/language visible.

### 7.3 Open Public Book Detail
- **Action:** Click on "QA Test Novel" in the catalog.
- **Verify:** Public book detail page loads with:
  - Book title, description, language
  - Chapter list
  - Author info
  - Word count / chapter count stats

### 7.4 Read a Chapter
- **Action:** Click on chapter 1 to open the reader.
- **Verify:**
  - Reader page loads with chapter content
  - ContentRenderer displays all blocks (paragraphs, headings, images)
  - TOC sidebar shows chapter list
  - Top bar shows chapter title

### 7.5 Read Translated Chapter
- **Action:** In the reader, find the language selector (TOC sidebar or top bar). Switch to "en" (English).
- **Verify:** Reader displays the English translation. Content matches what was translated in Scenario 6.

### 7.6 Reader Features
- **Action:** Test each reader feature:
  1. Theme customizer — click "Aa" button, change font/size/theme
  2. Keyboard navigation — press arrow keys, Home/End
  3. Click on chapter in TOC sidebar to navigate
- **Verify:** All features work. Theme changes apply immediately.

---

## Scenario 8: Chat with AI

**Goal:** Test the chat system including the new voice mode UI.

### 8.1 Start a New Chat
- **Action:** Go to Chat. Click "+ New". Select a model. Type "Tell me about the characters in my novel" and press Enter.
- **Verify:** Message sends. AI response streams in. Thinking mode toggle visible.

### 8.2 Voice Mode UI (Visual Only)
- **Action:**
  1. In the chat header, find the microphone icon (🎤)
  2. Click it to enter Voice Mode
  3. Verify overlay appears with: waveform area, transcript area, controls (Pause, Exit)
  4. Click settings gear (⚙️) in the overlay
  5. Verify Voice Settings panel opens with: STT/TTS source selectors, model dropdowns, language, sliders
  6. Close settings, then click "Exit Voice Mode"
- **Verify:** Overlay opens/closes cleanly. Settings panel shows all controls. Escape key exits voice mode.

### 8.3 Push-to-Talk Mic Button
- **Action:** In the chat input bar, find the mic icon (between attach and Think/Fast toggle).
- **Verify:** Mic icon is visible. (Actual recording requires microphone permission — just verify the button exists and is clickable.)

---

## Scenario 9: Entity Alive Toggle

**Goal:** Test the alive/dead toggle on glossary entities.

### 9.1 Find Extracted Entities
- **Action:** Go to the book's Glossary tab. Find an entity that was extracted (has "alive" badge).
- **Verify:** Green "alive" pill badge visible next to status badge.

### 9.2 Toggle to Dead
- **Action:** Click the "alive" badge on an entity.
- **Verify:** Badge changes to gray "dead". Entity stays in the list.

### 9.3 Toggle Back to Alive
- **Action:** Click the "dead" badge.
- **Verify:** Badge changes back to green "alive".

---

## Scenario 10: Wiki

**Goal:** Create and view a wiki article for the book.

### 10.1 Create Wiki Article
- **Action:** Go to Wiki tab. Click "New Article" or equivalent.
- **Verify:** Wiki editor opens. Title and body fields available.

### 10.2 Write Article
- **Action:** Create an article about the main character:
  - Title: character name
  - Body: description, abilities, relationships
  - Category/kind: "Character"
- **Verify:** Article saves. Appears in wiki article list.

### 10.3 Read Wiki Article
- **Action:** Click on the article in the wiki list.
- **Verify:** Article renders with proper formatting. Infobox/sidebar visible if configured.

---

## Scenario 11: Import

**Goal:** Test file import functionality.

### 11.1 Import a Text File
- **Action:** On Chapters tab, click "Import". Select a `.txt` file with Chinese content.
- **Verify:** Import dialog shows progress. Chapter appears in the list after import completes.

---

## Scenario 12: Cleanup

**Goal:** Test deletion and trash functionality.

### 12.1 Trash a Chapter
- **Action:** On Chapters tab, click the trash icon on a chapter. Confirm deletion.
- **Verify:** Chapter disappears from the list. Toast confirms "moved to trash".

### 12.2 View Trash
- **Action:** Go to Trash (`/trash`) in sidebar.
- **Verify:** Trashed chapter appears. Restore and permanent delete options visible.

### 12.3 Restore from Trash
- **Action:** Click "Restore" on the trashed chapter.
- **Verify:** Chapter disappears from trash. Reappears in the book's chapter list.

---

## Bug Report Template

For each issue found, record:

```markdown
### Bug: [Short title]
- **Scenario:** [Which scenario/step]
- **Expected:** [What should happen]
- **Actual:** [What happened]
- **Screenshot:** [Attach if available]
- **Severity:** Critical / High / Medium / Low
- **Browser:** [Chrome/Firefox/Safari + version]
```

---

## Review Summary Template

After completing all scenarios, write:

```markdown
## QA Walkthrough Summary

**Date:** [date]
**Tester:** [name/agent]
**Environment:** [localhost / staging / production]
**Browser:** [browser + version]

### Scenarios Completed
- [ ] 1. First Look — Navigate All Screens
- [ ] 2. Create a New Book
- [ ] 3. Glossary Extraction (AI-Powered)
- [ ] 4. Batch Extraction
- [ ] 5. Translate the Glossary
- [ ] 6. Translate a Chapter
- [ ] 7. Publish and Browse
- [ ] 8. Chat with AI
- [ ] 9. Entity Alive Toggle
- [ ] 10. Wiki
- [ ] 11. Import
- [ ] 12. Cleanup

### Bugs Found
[List bugs here]

### Overall Assessment
[Pass / Pass with issues / Fail]

### Notes
[Any observations about UX, performance, or suggestions]
```

---

*Last updated: 2026-04-11 — LoreWeave session 31*
