# 10 — Place or organization: not a classification error

`09` measured roughly two thirds of `organization` to be places. The obvious reading is *the model is
bad at classifying*, and the obvious fix is a better prompt. Both are wrong, and the data says so.

---

## 1. The evidence

Over the first 10 chapters, run against every extracted entity:

```
55 organizations · 41 carry a CLASSICAL PLACE SUFFIX (75%)
   鹿臺 紫霄宮 九間殿 相府 五關 終南山 汜水關 穿雲關 潼關 臨潼關 澠池縣 丞相府
   紫陽洞 比干府 九間大殿 西岐山 玉虛宮 靈鷲山元覺洞 五龍山雲霄洞 九宮山白鶴洞
   乾元山金光洞 陳塘關 金光洞 靈霄殿 白骨洞 寶德門 聚仙門 水晶宮 南天門 南都
   元戎府 西門 太廟 終南山玉柱洞 太師府 武成王黃飛虎帥府 西宮 …

14 carry NO place suffix — and they are the real organizations
   商 · 商朝 · 西周 · 截教 · 闡教 · 天庭 · 四海龍王 · 東伯侯 · 南伯侯 ·
   文書房 · 命館 · 西岐 · 東魯 · 孟津
```

Two things fall out immediately.

**The model is not blind.** 截教 and 闡教 — the two Daoist orders the entire novel is about — are
classified correctly, as are the dynasties and the celestial court. What it over-assigns to
`organization` is specifically the **place-shaped** things.

**Classical Chinese carries the type in the last character.** 山 mountain · 洞 cave · 殿 hall ·
府 mansion · 關 pass · 州 province · 宮 palace · 臺 terrace · 門 gate · 縣 county. The morphology is
doing ontology, deterministically, with no model involved — and on this sample its precision looks
close to perfect: of 23 entities the model called `location`, 17 carry the same suffixes, so the rule
*agrees* with the model wherever the model was right.

## 2. The diagnosis, and it is not "classification"

Look at what the misfiled entities have in common:

| entity | the place | the institution seated in it |
|---|---|---|
| 乾元山金光洞 | a cave on Mount Qianyuan | 太乙真人's lineage |
| 終南山玉柱洞 | a cave on Mount Zhongnan | 雲中子's school |
| 紫霄宮 | a palace | 鴻鈞's teaching seat |
| 太師府 | a mansion | the Grand Preceptor's office and household |
| 九間殿 | a hall | the court that sits in it |

> **`BTG-A28`.** **This is a MISSING-ENTITY error, not a classification error.** The world contains two
> things — a cave and a school — and the extractor was offered one slot, so it named the cave and typed
> it as the school. Every "wrong kind" here is a **collapsed pair**.
>
> That reframes the fix entirely. A better prompt makes the model choose the other half of the pair;
> it does not stop the halving. **Adjudicating which one it is, is the wrong question**: in a
> cultivation novel a master's cave *is* the sect, and picking either answer discards a real entity.

Not all of them are pairs — 鹿臺 is a terrace and nothing more, a plain misfile. So the design has to
handle both, and it should not pretend one story explains everything.

## 3. What the current mechanism cannot do, and why

Three gaps, and no prompt tweak closes any of them:

1. **The kinds have no definitions.** `book_kinds.description` is NULL for every adopted kind. The
   model is handed the bare words *"organization"* and *"location"* and falls back on its own priors,
   which in this genre correctly associate a cave with a school. The prompt is not wrong; it is empty.
2. **One entity, one kind.** The schema offers no way to say *a place that houses an institution*, so
   an entity that is both must be recorded as a lie.
3. **Nothing disagrees afterwards.** Extraction writes and no second reader ever objects. This is the
   same shape as every defect this project has recorded: *a check nothing consumes is decoration* —
   except here there is no check at all.

And the deepest one, which is this project's own hard-won lesson applied a level down:

> **`BTG-A29`.** The extraction call already asks a model to find entities, name them, alias them,
> describe them, fill 59 attributes **and** pick a kind. `03_two_jobs.md` measured what happens when
> one turn holds an intention while filling a form: it sacrifices one, and which one varies per run.
> **Kind assignment is the thing that loses**, and it loses in a way nothing downstream can see
> (`BTG-A27`).

## 4. What to add — five levers, ranked by evidence

**① Split the pair instead of adjudicating it.** The cave is a `location`; the school is an
`organization`; a relation joins them. `kg_edge_types` already declares directed typed edges with
`from_kinds`/`to_kinds`, so `SEAT_OF(organization → location)` is a row, not a new subsystem. This
**dissolves** the ambiguity rather than deciding it, and it recovers the entity that was being lost —
which is the whole finding of §2.

**② Derive the kind; do not ask for it.** This project's own `ASK-A2`: *never ask for the answer, ask
for the structure that determines it, then compute*. The model is bad at picking a label and good at
answering:

> *Can you walk into it?* · *Does it have members?* · *If the building burned down, would it still
> exist?*

Two easy questions produce four cells — place · organization · **both** (the pair of ①) · neither —
and the kind becomes a computation over answers instead of a guess. Better still, those answers belong
in the glossary's **EAV attributes**, where a human can see and correct them, rather than evaporating
as hidden prompt state.

**③ A deterministic morphology lint that FLAGS, never rewrites.** Free, no model, ~75% recall on this
sample and near-perfect precision. But it must only raise a **conflict** (`BTG-A20`'s channel): 金光洞
genuinely is both, and a rule that silently rewrote it would destroy the very entity ① is trying to
recover. Flag-not-fix is also what keeps it honest — a morphology rule for Chinese does not generalise
to a language without the suffix system, and a flag degrades to noise where a rewrite would corrupt.

**④ Kind descriptions, written CONTRASTIVELY.** A NULL column that already exists, so this is a data
fix. And they must be written against each other rather than in isolation — *"a body of people acting
together; it survives the loss of its building"* discriminates, where *"an organization"* does not.

**⑤ Let the KG disagree.** Once edges exist, an entity that is the object of `MEMBER_OF` is an
organization and one that is the object of `LOCATED_IN` is a place. A kind that contradicts its own
relations is a detectable conflict and a **genuine second source** — which `09` §4.3 said the aggregate
signal needs before it can be trusted.

## 5. What to do first

**① and ③ together**, and in that order of importance.

③ is an afternoon and needs no model: it produces a ranked list of ~41 conflicts on ten chapters, which
is the first real subject the human-in-the-loop channel has ever had. ① is the design decision that
makes the flags *actionable* — without it, a human reviewing 金光洞 has only two wrong answers to
choose between.

② is the deeper fix and the most invasive: it changes what the extraction prompt asks for, which is the
platform's pipeline rather than this tier's. It should be proposed there **with this measurement
attached**, because the argument for it is not "prompts could be better" — it is *the current shape
loses an entity per pair, silently, and the sweep cannot see it*.

④ is nearly free and should just be done, but on its own it only moves the model from one guess to a
better guess.

⑤ waits on the KG.

## 6. What would falsify this

* **If ③'s flags turn out to be mostly plain misfiles rather than pairs**, then `BTG-A28` is wrong,
  this really is a classification problem, and ④ plus ② are the whole answer. Reading the 41 flags is
  how that gets settled, and it has not been done — §2's table is five examples, not a survey.
* **If the suffix rule's precision drops on later chapters**, it stays a hint and never becomes a gate.
  Ten court-politics chapters are a narrow sample; the mountains and caves arrive in bulk later.
* **If a non-CJK book shows the same confusion**, morphology was never the mechanism and ② is the only
  lever that transfers.
