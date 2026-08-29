# T33 — causal labelling sheet

labelled_by: 

> Fill each `LABEL:` with exactly one of `causes` / `precedes` / `unknown`.
> `causes` = the earlier event DIRECTLY brings about or enables the later one.
> `precedes` = it clearly happens after, but you cannot show causation.
> `unknown` = you cannot tell, or they are unrelated. **Prefer `unknown`** — the row's
> own criterion says a wrong order is worse than an absent one.

Ordering within a chapter is `Event.event_order`, present on every event in scope.
Read from the store the deployment DECLARES (`age`), not from Neo4j — reading the
wrong store is what made an earlier draft report the extractor as never having run.

```json
{
 "project_id": "019fefde-2f6b-7017-87de-c6b390a170c3",
 "chapters": [
  "019fb89f-ecdb-746f-b543-5e8265c5febe",
  "019fb89f-ecfe-7886-8ed5-a045c0f51f33"
 ],
 "causal_pass_ran": true,
 "pairs": {
  "P1": {
   "earlier": "a2ca86d82db0453f8e225f30230f83d1",
   "later": "b79be68f465a98bb1ae6d416c2b6c5d4",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P2": {
   "earlier": "b79be68f465a98bb1ae6d416c2b6c5d4",
   "later": "ea014caa45e9f2d5f28b0cfd94c31449",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P3": {
   "earlier": "ea014caa45e9f2d5f28b0cfd94c31449",
   "later": "4a073be929b11adb0d7fd07e5ab7ff7e",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P4": {
   "earlier": "4a073be929b11adb0d7fd07e5ab7ff7e",
   "later": "1a2d89457134325a3be71812227c5e0f",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P5": {
   "earlier": "1a2d89457134325a3be71812227c5e0f",
   "later": "f9cbaa54403c105f00883962b8e3f10d",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P6": {
   "earlier": "f9cbaa54403c105f00883962b8e3f10d",
   "later": "522b21e949449929393a3fba46f5e224",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P7": {
   "earlier": "522b21e949449929393a3fba46f5e224",
   "later": "432ca14d25d63f1d4e9fd2260eeb7dbf",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P8": {
   "earlier": "432ca14d25d63f1d4e9fd2260eeb7dbf",
   "later": "3ecf9a16395d204ddb5c7a0a9f1640fa",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P9": {
   "earlier": "3ecf9a16395d204ddb5c7a0a9f1640fa",
   "later": "8c20094ee5a0b1fc4224e19f95d82feb",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P10": {
   "earlier": "8c20094ee5a0b1fc4224e19f95d82feb",
   "later": "beb425af38fc5904c7bd448c6a4b0f86",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P11": {
   "earlier": "beb425af38fc5904c7bd448c6a4b0f86",
   "later": "e249b2401706c79db00a1e913ecedbb8",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P12": {
   "earlier": "e249b2401706c79db00a1e913ecedbb8",
   "later": "b6829af2bdf6c07ac597b4b26e9f83da",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P13": {
   "earlier": "b6829af2bdf6c07ac597b4b26e9f83da",
   "later": "f8312961c89be11c2cc45682e456230e",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P14": {
   "earlier": "f8312961c89be11c2cc45682e456230e",
   "later": "6300be530f41b026b846f0e88617ecb5",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P15": {
   "earlier": "6300be530f41b026b846f0e88617ecb5",
   "later": "a4b5c135677008bedd6ebd44a3cbf813",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P16": {
   "earlier": "a4b5c135677008bedd6ebd44a3cbf813",
   "later": "a5b12d4fa00626aef904ba2baa5fb8fe",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P17": {
   "earlier": "a5b12d4fa00626aef904ba2baa5fb8fe",
   "later": "bf6e388f04b9f22423516100d38d9614",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P18": {
   "earlier": "bf6e388f04b9f22423516100d38d9614",
   "later": "e553b454fe91e28859ba216ef353a093",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P19": {
   "earlier": "e553b454fe91e28859ba216ef353a093",
   "later": "c06a8af06a07bb5d66e0446e3da4f45b",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P20": {
   "earlier": "a2ca86d82db0453f8e225f30230f83d1",
   "later": "ea014caa45e9f2d5f28b0cfd94c31449",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  }
 },
 "system_predicted": {
  "P18": "causes",
  "P9": "precedes"
 }
}
```

#### PAIR P1

**earlier** — 伊尹輔佐成湯
> 伊尹在有莘之野耕作，後輔佐成湯。

**later** — 伊尹輔佐成湯伐桀
> 伊尹輔佐成湯討伐桀王，將其放逐至南巢。

LABEL:

#### PAIR P2

**earlier** — 伊尹輔佐成湯伐桀
> 伊尹輔佐成湯討伐桀王，將其放逐至南巢。

**later** — 紂王進香女媧宮
> 紂王率領文武百官前往女媧宮進香。

LABEL:

#### PAIR P3

**earlier** — 紂王進香女媧宮
> 紂王率領文武百官前往女媧宮進香。

**later** — 伏羲畫卦
> 伏羲在陰陽之前畫出了八卦。

LABEL:

#### PAIR P4

**earlier** — 伏羲畫卦
> 伏羲在陰陽之前畫出了八卦。

**later** — 商容建議進香女媧宮
> 商容建議紂王於三月十五日前往女媧宮進香。

LABEL:

#### PAIR P5

**earlier** — 商容建議進香女媧宮
> 商容建議紂王於三月十五日前往女媧宮進香。

**later** — 女媧召喚三妖
> 女媧召喚三妖，並密旨讓她們潛入宮中惑亂君心。

LABEL:

#### PAIR P6

**earlier** — 女媧召喚三妖
> 女媧召喚三妖，並密旨讓她們潛入宮中惑亂君心。

**later** — 帝乙崩
> 帝乙在位三十年後去世。

LABEL:

#### PAIR P7

**earlier** — 帝乙崩
> 帝乙在位三十年後去世。

**later** — 女媧大怒
> 女媧看到紂王的詩句後大怒，決定降下災禍。

LABEL:

#### PAIR P8

**earlier** — 女媧大怒
> 女媧看到紂王的詩句後大怒，決定降下災禍。

**later** — 帝乙生三子
> 帝乙在御園遊玩時生下三個兒子：微子啟、微子衍和壽王。

LABEL:

#### PAIR P9

**earlier** — 帝乙生三子
> 帝乙在御園遊玩時生下三個兒子：微子啟、微子衍和壽王。

**later** — 成湯即位
> 成湯在諸侯推舉下即位，定都亳地。

LABEL:

#### PAIR P10

**earlier** — 成湯即位
> 成湯在諸侯推舉下即位，定都亳地。

**later** — 袁福通反叛
> 紂王七年二月，北海七十二路諸侯袁福通發動叛亂。

LABEL:

#### PAIR P11

**earlier** — 袁福通反叛
> 紂王七年二月，北海七十二路諸侯袁福通發動叛亂。

**later** — 成湯造亳
> 成湯在亳地建立都城。

LABEL:

#### PAIR P12

**earlier** — 成湯造亳
> 成湯在亳地建立都城。

**later** — 禹王治水
> 禹王治理洪災，平定水患。

LABEL:

#### PAIR P13

**earlier** — 禹王治水
> 禹王治理洪災，平定水患。

**later** — 桀王無道
> 桀王失德，導致天下大亂。

LABEL:

#### PAIR P14

**earlier** — 桀王無道
> 桀王失德，導致天下大亂。

**later** — 紂王即位
> 帝乙去世後，由聞仲輔佐，立壽王為天子，即紂王，定都朝歌。

LABEL:

#### PAIR P15

**earlier** — 紂王即位
> 帝乙去世後，由聞仲輔佐，立壽王為天子，即紂王，定都朝歌。

**later** — 燧人取火
> 燧人取火，使人類免於生食。

LABEL:

#### PAIR P16

**earlier** — 燧人取火
> 燧人取火，使人類免於生食。

**later** — 紂王在女媧宮作詩
> 紂王在女媧宮行宮的粉壁上作詩褻瀆女媧。

LABEL:

#### PAIR P17

**earlier** — 紂王在女媧宮作詩
> 紂王在女媧宮行宮的粉壁上作詩褻瀆女媧。

**later** — 盤古開天闢地
> 盤古在混沌初分時開天闢地。

LABEL:

#### PAIR P18

**earlier** — 盤古開天闢地
> 盤古在混沌初分時開天闢地。

**later** — 神農治世
> 神農嘗百草以治世。

LABEL:

#### PAIR P19

**earlier** — 神農治世
> 神農嘗百草以治世。

**later** — 紂王聽從費仲建議
> 紂王因思念女媧而煩悶，聽從費仲建議，決定向四路諸侯徵召美女。

LABEL:

#### PAIR P20

**earlier** — 伊尹輔佐成湯
> 伊尹在有莘之野耕作，後輔佐成湯。

**later** — 紂王進香女媧宮
> 紂王率領文武百官前往女媧宮進香。

LABEL:
