# Golden Candidates — staging area for gold-set expansion (cycle 74e)

**Status: UN-ANNOTATED candidates. NOT part of the active eval yet.**

These are public-domain chapter excerpts sourced as candidates to grow the
`golden_chapters/` gold set (audit eval-flaw #2: 9 chapters, several with only
1 gold relation, no confidence intervals). Each `chapter.txt` here is **verbatim
source text** fetched from a public-domain repository. The `expected.yaml`
(ground-truth annotation) is **deliberately not written yet** — annotation is the
human-adjudicated step so the gold does not become another LLM grading another
LLM (the same self-reinforcement trap, one level up).

## Why these chapters

Selection priority = **RELATION density**, because RELATION is the weakest and
most under-sampled category in the current gold set (entity 0.93–0.99, event
0.945–0.983, relation 0.69–0.94; 3 chapters have exactly 1 gold relation, so a
single judge flip swings that chapter's relation recall 0→1.0). New chapters are
chosen to be kinship/authority/alliance-dense so they add many gold relations.

| Candidate dir | Source (PD) | Lang | Why (target predicate coverage) |
|---|---|---|---|
| `sense_sensibility_ch01` | Sense and Sensibility ch.1 — Jane Austen, PG #161 | en | Kinship + inheritance: `child_of`, `sibling_of`, `married_to`, `born_from` (Henry Dashwood = nephew of old owner; son by former marriage; three daughters by present wife). |
| `pride_prejudice_ch03` | Pride and Prejudice ch.3 — Jane Austen, PG #1342 | en | Social/courting: `knows`, `courts`, `member_of` (Bingley ↔ Bennets, Lady Lucas, Sir William). Same book as existing `pride_prejudice_ch01` but a distinct chapter. |
| `three_kingdoms_zh_ch01` | 三國演義 第一回 (Luo Guanzhong, c.14thC) — zh.wikisource | zh | Sworn-brotherhood + alliance: 劉備/關羽/張飛 結為兄弟 with explicit elder→younger ordering (`sibling_of`), `allied`/`serves`. CJK relation extraction stress test. |
| `dream_red_chamber_zh_ch03` | 紅樓夢 第三回 (Cao Xueqin, c.1760) — zh.wikisource | zh | Kinship goldmine: 黛玉 ↔ 外祖母(賈母) ↔ 賈赦/賈政 ↔ 舅母/嫂子. Dense `child_of`/`sibling_of`/`married_to` across three generations; tests honorific/kinship-term canonicalization. |
| `luc_van_tien_vi` | Lục Vân Tiên opening — Nguyễn Đình Chiểu (d.1888, pub.1889) — vi.wikisource | vi | **Real canonical PD source** (vs. the existing VN paraphrase fixtures). Mentorship-focused: `disciple_of`/`mentor_of` (Vân Tiên ↔ thầy/tôn sư) + `child_of`. Verse (lục bát) — harder to annotate; entity density modest but adds VN mentorship coverage the kinship-only VN fixtures lack. |

## Adjudication workflow (the human-in-the-loop step)

1. **Draft** (LLM-assisted, optional): a strong model **NOT in the extraction/judge
   loop** (frontier cloud e.g. Claude — calibration-only is acceptable per
   `feedback_local_llm_first_cloud_is_fallback`; **never** the Qwen extractor
   `019e6a20` / filter `019e5650`) drafts candidate entities/relations/events,
   conservatively. Optionally 2–3 diverse-architecture drafters → disagreements
   mark the hard cases.
2. **Adjudicate** (required, human): the user reviews/corrects every label;
   native-speaker check for zh. This is what makes it *gold*.
3. **Consistency-check** (automated): grep every claimed alias against
   `chapter.txt` (`feedback_test_fixture_aliases_must_be_in_source` — world-knowledge
   aliases not literal in-text = wrong extractor expectation); schema-validate;
   `pytest tests/unit/test_eval_harness.py` for YAML round-trip.
4. **Promote**: move the dir into `golden_chapters/` with a finished
   `expected.yaml` (entity kinds synced to the prompt enum; predicates in the
   canonical 28-vocab).

## Open items needing user decision

- **Vietnamese**: addressed — `luc_van_tien_vi` is now a real canonical PD source
  (Lục Vân Tiên, Nguyễn Đình Chiểu, fully PD), replacing the paraphrase concern for
  this slot. It is **verse** (lục bát), so annotation should expect verse phrasing;
  entity density is modest. (Truyện Kiều was tried first but the WebFetch helper
  false-refused it as "copyright" despite Nguyễn Du d.1820 — a Kiều excerpt can still
  be added later by pasting manually if more VN volume is wanted.)
- **ja / ko**: `patterns/{ja,ko}.py` detectors exist but there is **no gold** for
  them. Optional coverage add (e.g. a Tale of Genji kinship excerpt) — only if you
  want language breadth beyond en/zh/vi.
- **Deepen existing 9 chapters**: orthogonal to new chapters — raising the
  single-relation chapters' per-chapter denominators is a cheap, high-value pass.
