# Spec — A1 per-language intent routing + A7 script-aware prose split

**Date:** 2026-07-06 · **Standard:** [`docs/standards/multilingual.md`](../standards/multilingual.md) (ML-1, ML-3) · **Track:** Area 7 "P4" — the last two open bias sites (A1, A7) after A2–A6 shipped.

## Why

Two remaining English-first rule paths from the enterprise audit:

- **A1 — intent classifier (`knowledge-service/app/context/intent/classifier.py`).** The 5 intent regexes (relational / historical-strong / historical-weak / recent / relational-strong) are 100% English. A live **interim** degrade-open exists (branch 4b: any non-ASCII letter → blanket `RELATIONAL`/2-hop), so non-English isn't *starved*, but every zh/ja/ko/vi query gets the **same** intent regardless of what it actually asks — "告诉我关于凯" (SPECIFIC_ENTITY) and "凯和林是什么关系" (RELATIONAL) both route RELATIONAL. That's a coarse floor, not routing.
- **A7 — prose sentence splitter (`frontend/src/features/chat/utils/proseHunks.ts`).** `SENTENCE_SPLIT` already handles CJK terminators (。！？) but the Latin dialogue-guard `\s+(?![a-z])` is ASCII-only. A Vietnamese lowercase-diacritic dialogue tag — `«Chạy!» ông nói` — has `ông` starting with `ô` (not `[a-z]`), so the guard fails and the tag splits into a wrong sentence boundary.

## A1 — design

**Approach: per-language keyword registry, unioned into the cascade regexes** (not langdetect dispatch — detection misfires on short queries, and disjoint scripts make a union safe: a CJK keyword can never match ASCII text, so English stays byte-identical).

- New `app/context/intent/lang/{en,zh,ja,ko,vi}.py` — one module per language, each exporting five keyword tuples (`HISTORICAL_STRONG`, `HISTORICAL_WEAK`, `RECENT`, `RELATIONAL_KEYWORDS`, `RELATIONAL_STRONG`). English keywords move verbatim from `classifier.py` (byte-identical) into `en.py`.
- New `app/context/intent/lang/__init__.py` — concatenates every language's list per category and compiles ONE `re.Pattern` per category (IGNORECASE). This is the ML-1 per-language registry shape (`get_intent_markers()` for introspection) with a union-compile for the hot path.
- `classifier.py` imports the compiled unions; the priority cascade is unchanged in logic.
- **Reorder the degrade-net.** Today branch 4b fires before SPECIFIC_ENTITY, so a non-ASCII query with a clear entity is hijacked to RELATIONAL. Move it to fire **only in place of GENERAL** — i.e. a non-ASCII query that produced no cascade signal AND no entity degrades to RELATIONAL/2-hop (better than the narrow 1-hop GENERAL), while a non-ASCII query WITH an entity or a real keyword routes correctly. English (pure-ASCII) never enters the net → byte-identical.

**Keyword sets** (common, unambiguous; disjoint scripts; degrade-net still backstops anything unmatched):
- RELATIONAL: zh 认识/知道/见过/遇见/关系/之间/朋友/敌人/结婚/结盟/对手 · ja 知って/会った/出会/関係/友達/敵/結婚/同盟 · ko 알/만났/관계/사이/친구/적/결혼/동맹 · vi biết/quen/gặp/quan hệ/giữa/bạn/kẻ thù/kết hôn/liên minh
- HISTORICAL: zh 很久以前/多年前/最初/原本/曾经 · ja 昔/かつて/最初は/元々 · ko 오래전/원래/처음에/한때 · vi ngày xưa/nhiều năm trước/ban đầu/từng
- RECENT: zh 刚刚/现在/此刻/目前/这一章 · ja たった今/今/現在/この章 · ko 방금/지금/현재/이 장 · vi vừa nãy/ngay bây giờ/hiện tại/chương này

**Scope guard.** These are *keyword* sets (rule-based, degrade-open), not a per-language ML classifier. Uncovered scripts (ar/th/hi/…) keep the non-ASCII degrade-net. A real classifier is out of scope (would be an LLM/embedding call, not a rule path).

### A1 acceptance
- The 50-query English golden fixture accuracy stays ≥ 0.80 (English behavior byte-identical — regression lock).
- New multilingual golden cases (zh/ja/ko/vi, ≥2 per language across specific/relational/recent/historical) route to their correct intent, NOT blanket RELATIONAL.
- A non-ASCII query with no signal + no entity still degrades to RELATIONAL (net preserved).
- Deterministic; empty → GENERAL; p95 < 15ms.

## A7 — design

Change the dialogue-guard lookahead from ASCII `(?![a-z])` to Unicode `(?!\p{Ll})` and add the `u` flag to `SENTENCE_SPLIT`. `\p{Ll}` (lowercase letter, any script) covers Latin + Vietnamese diacritics + accented lowercase, so a lowercase-continuation dialogue tag in any Latin-script language is guarded. CJK has no case → `\p{Ll}` doesn't match ideographs → CJK after a Latin terminator still splits (correct; the CJK-terminator branch is separate). Abbreviation guard ("e.g. foo") is preserved (`foo` is `\p{Ll}`).

### A7 acceptance
- `«Chạy!» ông nói.` (or `"Chạy!" ông nói.`) stays ONE unit (dialogue tag not split).
- Existing English cases unchanged: `"Run!" she said. He froze.` → `['"Run!" she said.', 'He froze.']`.
- CJK `田中は言った。彼は笑った。` still splits on 。.

## Files
- BE: `app/context/intent/lang/{__init__,en,zh,ja,ko,vi}.py` (new), `app/context/intent/classifier.py` (edit), `tests/unit/test_intent_classifier.py` + `fixtures/intent_queries.yaml` (multilingual cases).
- FE: `frontend/src/features/chat/utils/proseHunks.ts` (1-line regex), `__tests__/proseHunks.test.ts` (cases).
- Docs: `multilingual.md` bias-site list (A1/A7 → ✅).

## Out of scope / deferred
- Per-language ML/embedding intent classifier (`D-ML-INTENT-ML` — only if the keyword sets prove insufficient in eval).
- Native-speaker validation of the keyword sets (the sets are common-word conservative; an eval pass with native review can tune them later).
