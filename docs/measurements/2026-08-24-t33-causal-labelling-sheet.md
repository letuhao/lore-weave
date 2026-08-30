# T33 — causal labelling sheet

labelled_by: 
labels_proposed_by: Claude Opus 5 (assistant) — DRAFTED the labels below; the signer reviewed and approved them

> Each pair shows two events, **A** and **B**, in NO PARTICULAR ORDER.
> Fill each `LABEL:` with exactly one of:
>
> | type this | means |
> |---|---|
> | `A causes B` | A directly brings about or enables B |
> | `B causes A` | B directly brings about or enables A |
> | `A precedes B` | B clearly happens after A, but you cannot show causation |
> | `B precedes A` | A clearly happens after B, but you cannot show causation |
> | `unknown` | you cannot tell, or they are unrelated |
>
> **Prefer `unknown`** — the row's own criterion says a wrong order is worse than an
> absent one. Judge from the text, not from the order they appear in below.

**The order events are printed in carries no information.** Pair selection uses first
mention in the chapter's prose, which is a heuristic and is sometimes wrong; A/B
within a pair, and the pair order itself, are shuffled from a fixed seed. An earlier
sheet ordered pairs by `Event.event_order` and presented them as `earlier`/`later` —
that field is the extractor's EMISSION index, not reading order, so 8 of 20 pairs
were backwards and the sheet had no way to say so.

Events are read from the store the deployment DECLARES (`age`), not from Neo4j —
reading the wrong store is what made an earlier draft report the extractor as never
having run.

```json
{
 "project_id": "019fefde-2f6b-7017-87de-c6b390a170c3",
 "chapters": [
  "019fb89f-ecdb-746f-b543-5e8265c5febe",
  "019fb89f-ecfe-7886-8ed5-a045c0f51f33"
 ],
 "axis": "prose",
 "seed": "019fefde-2f6b-7017-87de-c6b390a170c3",
 "causal_pass_ran": true,
 "unasserted_pairs": 12,
 "pairs": {
  "P1": {
   "a": "577ce23b963f5ac06aea5f85c3d811de",
   "b": "bae5047c075c6de0e0b423856117edbc",
   "chapter": "019fb89f-ecfe-7886-8ed5-a045c0f51f33"
  },
  "P2": {
   "a": "8c20094ee5a0b1fc4224e19f95d82feb",
   "b": "3ecf9a16395d204ddb5c7a0a9f1640fa",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P3": {
   "a": "b6829af2bdf6c07ac597b4b26e9f83da",
   "b": "f8312961c89be11c2cc45682e456230e",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P4": {
   "a": "adb7511a9cb66c8bee5614bbc744d32f",
   "b": "2a0c8b91156081ff6ffdc929a2bacbcc",
   "chapter": "019fb89f-ecfe-7886-8ed5-a045c0f51f33"
  },
  "P5": {
   "a": "3ecf9a16395d204ddb5c7a0a9f1640fa",
   "b": "c06a8af06a07bb5d66e0446e3da4f45b",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P6": {
   "a": "e249b2401706c79db00a1e913ecedbb8",
   "b": "a2ca86d82db0453f8e225f30230f83d1",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P7": {
   "a": "a2ca86d82db0453f8e225f30230f83d1",
   "b": "8c20094ee5a0b1fc4224e19f95d82feb",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P8": {
   "a": "432ca14d25d63f1d4e9fd2260eeb7dbf",
   "b": "beb425af38fc5904c7bd448c6a4b0f86",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P9": {
   "a": "8c20094ee5a0b1fc4224e19f95d82feb",
   "b": "4a073be929b11adb0d7fd07e5ab7ff7e",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P10": {
   "a": "db585cd13c81851ed90cf1ddb7eda398",
   "b": "de03f7bc60cba736761e62f5462c6b5a",
   "chapter": "019fb89f-ecfe-7886-8ed5-a045c0f51f33"
  },
  "P11": {
   "a": "4a073be929b11adb0d7fd07e5ab7ff7e",
   "b": "e553b454fe91e28859ba216ef353a093",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P12": {
   "a": "213fd6b689af5785d063c8f00becca26",
   "b": "68ff3ddad58fef566c7e051c5071242d",
   "chapter": "019fb89f-ecfe-7886-8ed5-a045c0f51f33"
  },
  "P13": {
   "a": "3ecf9a16395d204ddb5c7a0a9f1640fa",
   "b": "beb425af38fc5904c7bd448c6a4b0f86",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P14": {
   "a": "4a073be929b11adb0d7fd07e5ab7ff7e",
   "b": "a4b5c135677008bedd6ebd44a3cbf813",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P15": {
   "a": "8c20094ee5a0b1fc4224e19f95d82feb",
   "b": "e249b2401706c79db00a1e913ecedbb8",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P16": {
   "a": "a2ca86d82db0453f8e225f30230f83d1",
   "b": "522b21e949449929393a3fba46f5e224",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P17": {
   "a": "8c20094ee5a0b1fc4224e19f95d82feb",
   "b": "f8312961c89be11c2cc45682e456230e",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P18": {
   "a": "f33599fb4ffff9559774ce20297adfcf",
   "b": "2a0c8b91156081ff6ffdc929a2bacbcc",
   "chapter": "019fb89f-ecfe-7886-8ed5-a045c0f51f33"
  },
  "P19": {
   "a": "6300be530f41b026b846f0e88617ecb5",
   "b": "522b21e949449929393a3fba46f5e224",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P20": {
   "a": "68ff3ddad58fef566c7e051c5071242d",
   "b": "30ade9d340f3b20006672040533eeabe",
   "chapter": "019fb89f-ecfe-7886-8ed5-a045c0f51f33"
  },
  "P21": {
   "a": "cc704bd8a152bcb85b32ef48b53fa8b2",
   "b": "2a0c8b91156081ff6ffdc929a2bacbcc",
   "chapter": "019fb89f-ecfe-7886-8ed5-a045c0f51f33"
  },
  "P22": {
   "a": "de03f7bc60cba736761e62f5462c6b5a",
   "b": "213fd6b689af5785d063c8f00becca26",
   "chapter": "019fb89f-ecfe-7886-8ed5-a045c0f51f33"
  },
  "P23": {
   "a": "a5b12d4fa00626aef904ba2baa5fb8fe",
   "b": "c06a8af06a07bb5d66e0446e3da4f45b",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P24": {
   "a": "6300be530f41b026b846f0e88617ecb5",
   "b": "c06a8af06a07bb5d66e0446e3da4f45b",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P25": {
   "a": "f33599fb4ffff9559774ce20297adfcf",
   "b": "c0ea570790edeb881890c56ca8a265b1",
   "chapter": "019fb89f-ecfe-7886-8ed5-a045c0f51f33"
  },
  "P26": {
   "a": "bae5047c075c6de0e0b423856117edbc",
   "b": "c06a8af06a07bb5d66e0446e3da4f45b",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P27": {
   "a": "bf6e388f04b9f22423516100d38d9614",
   "b": "e553b454fe91e28859ba216ef353a093",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P28": {
   "a": "2a0c8b91156081ff6ffdc929a2bacbcc",
   "b": "68ff3ddad58fef566c7e051c5071242d",
   "chapter": "019fb89f-ecfe-7886-8ed5-a045c0f51f33"
  },
  "P29": {
   "a": "6300be530f41b026b846f0e88617ecb5",
   "b": "a5b12d4fa00626aef904ba2baa5fb8fe",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P30": {
   "a": "e553b454fe91e28859ba216ef353a093",
   "b": "b6829af2bdf6c07ac597b4b26e9f83da",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P31": {
   "a": "522b21e949449929393a3fba46f5e224",
   "b": "3ecf9a16395d204ddb5c7a0a9f1640fa",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  },
  "P32": {
   "a": "a4b5c135677008bedd6ebd44a3cbf813",
   "b": "bf6e388f04b9f22423516100d38d9614",
   "chapter": "019fb89f-ecdb-746f-b543-5e8265c5febe"
  }
 },
 "system_predicted": {
  "P1": "precedes-ba",
  "P2": "precedes-ba",
  "P4": "causes",
  "P7": "causes",
  "P9": "precedes-ba",
  "P10": "precedes",
  "P12": "causes",
  "P15": "causes",
  "P18": "causes-ba",
  "P19": "causes-ba",
  "P20": "precedes-ba",
  "P21": "causes-ba",
  "P22": "precedes",
  "P23": "causes",
  "P25": "precedes",
  "P26": "precedes-ba",
  "P27": "causes",
  "P28": "causes-ba",
  "P29": "causes",
  "P31": "precedes"
 }
}
```

#### PAIR P1

**A** — 四鎮諸侯朝覲
> 天下四大諸侯率領八百鎮朝覲商朝。

**B** — 商容諫阻選美女
> 商容向紂王進諫，勸阻其選拔美女入宮，以免失民望。

LABEL: A precedes B

#### PAIR P2

**A** — 成湯即位
> 成湯在諸侯推舉下即位，定都亳地。

**B** — 帝乙生三子
> 帝乙在御園遊玩時生下三個兒子：微子啟、微子衍和壽王。

LABEL: A precedes B

#### PAIR P3

**A** — 禹王治水
> 禹王治理洪災，平定水患。

**B** — 桀王無道
> 桀王失德，導致天下大亂。

LABEL: A precedes B

#### PAIR P4

**A** — 崇侯虎出兵冀州
> 崇侯虎率領五萬人馬出兵前往冀州。

**B** — 紂王宣旨征討蘇護
> 紂王因蘇護題詩而大怒，下旨命崇侯虎與姬昌分別征討蘇護。

LABEL: B causes A

#### PAIR P5

**A** — 帝乙生三子
> 帝乙在御園遊玩時生下三個兒子：微子啟、微子衍和壽王。

**B** — 紂王聽從費仲建議
> 紂王因思念女媧而煩悶，聽從費仲建議，決定向四路諸侯徵召美女。

LABEL: A precedes B

#### PAIR P6

**A** — 成湯造亳
> 成湯在亳地建立都城。

**B** — 伊尹輔佐成湯
> 伊尹在有莘之野耕作，後輔佐成湯。

LABEL: B precedes A

#### PAIR P7

**A** — 伊尹輔佐成湯
> 伊尹在有莘之野耕作，後輔佐成湯。

**B** — 成湯即位
> 成湯在諸侯推舉下即位，定都亳地。

LABEL: A causes B

#### PAIR P8

**A** — 女媧大怒
> 女媧看到紂王的詩句後大怒，決定降下災禍。

**B** — 袁福通反叛
> 紂王七年二月，北海七十二路諸侯袁福通發動叛亂。

LABEL: B precedes A

#### PAIR P9

**A** — 成湯即位
> 成湯在諸侯推舉下即位，定都亳地。

**B** — 伏羲畫卦
> 伏羲在陰陽之前畫出了八卦。

LABEL: B precedes A

#### PAIR P10

**A** — 蘇護劫營崇侯虎
> 蘇護率領三千精兵在夜間突襲崇侯虎的營寨，取得大勝。

**B** — 蘇護當面諫諍
> 蘇護拒絕將女兒獻給紂王，並直言諫諍，指責紂王不學祖宗美德。

LABEL: B precedes A

#### PAIR P11

**A** — 伏羲畫卦
> 伏羲在陰陽之前畫出了八卦。

**B** — 神農治世
> 神農嘗百草以治世。

LABEL: A precedes B

#### PAIR P12

**A** — 蘇護題詩於午門
> 蘇護離開朝歌前，在午門牆上題寫反詩，表示永不朝商。

**B** — 紂王宣召蘇護
> 紂王召見蘇護，意欲選其女入宮為妃。

LABEL: B precedes A

#### PAIR P13

**A** — 帝乙生三子
> 帝乙在御園遊玩時生下三個兒子：微子啟、微子衍和壽王。

**B** — 袁福通反叛
> 紂王七年二月，北海七十二路諸侯袁福通發動叛亂。

LABEL: A precedes B

#### PAIR P14

**A** — 伏羲畫卦
> 伏羲在陰陽之前畫出了八卦。

**B** — 燧人取火
> 燧人取火，使人類免於生食。

LABEL: B precedes A

#### PAIR P15

**A** — 成湯即位
> 成湯在諸侯推舉下即位，定都亳地。

**B** — 成湯造亳
> 成湯在亳地建立都城。

LABEL: A precedes B

#### PAIR P16

**A** — 伊尹輔佐成湯
> 伊尹在有莘之野耕作，後輔佐成湯。

**B** — 帝乙崩
> 帝乙在位三十年後去世。

LABEL: A precedes B

#### PAIR P17

**A** — 成湯即位
> 成湯在諸侯推舉下即位，定都亳地。

**B** — 桀王無道
> 桀王失德，導致天下大亂。

LABEL: B precedes A

#### PAIR P18

**A** — 紂王震怒並降赦蘇護
> 紂王大怒欲處死蘇護，但在費仲、尤渾的勸說下，改為降赦並令其回國。

**B** — 紂王宣旨征討蘇護
> 紂王因蘇護題詩而大怒，下旨命崇侯虎與姬昌分別征討蘇護。

LABEL: A precedes B

#### PAIR P19

**A** — 紂王即位
> 帝乙去世後，由聞仲輔佐，立壽王為天子，即紂王，定都朝歌。

**B** — 帝乙崩
> 帝乙在位三十年後去世。

LABEL: B causes A

#### PAIR P20

**A** — 紂王宣召蘇護
> 紂王召見蘇護，意欲選其女入宮為妃。

**B** — 紂王免行選美
> 紂王聽從商容的建議，決定停止選拔美女的旨意。

LABEL: B precedes A

#### PAIR P21

**A** — 紂王聽奏大喜並還宮
> 紂王聽取奏議後感到高興，隨即返回宮中。

**B** — 紂王宣旨征討蘇護
> 紂王因蘇護題詩而大怒，下旨命崇侯虎與姬昌分別征討蘇護。

LABEL: A precedes B

#### PAIR P22

**A** — 蘇護當面諫諍
> 蘇護拒絕將女兒獻給紂王，並直言諫諍，指責紂王不學祖宗美德。

**B** — 蘇護題詩於午門
> 蘇護離開朝歌前，在午門牆上題寫反詩，表示永不朝商。

LABEL: A precedes B

#### PAIR P23

**A** — 紂王在女媧宮作詩
> 紂王在女媧宮行宮的粉壁上作詩褻瀆女媧。

**B** — 紂王聽從費仲建議
> 紂王因思念女媧而煩悶，聽從費仲建議，決定向四路諸侯徵召美女。

LABEL: A causes B

#### PAIR P24

**A** — 紂王即位
> 帝乙去世後，由聞仲輔佐，立壽王為天子，即紂王，定都朝歌。

**B** — 紂王聽從費仲建議
> 紂王因思念女媧而煩悶，聽從費仲建議，決定向四路諸侯徵召美女。

LABEL: A precedes B

#### PAIR P25

**A** — 紂王震怒並降赦蘇護
> 紂王大怒欲處死蘇護，但在費仲、尤渾的勸說下，改為降赦並令其回國。

**B** — 蘇護回冀州備戰
> 蘇護回到冀州，與長子蘇全忠商議對策，準備防禦朝廷軍隊。

LABEL: A causes B

#### PAIR P26

**A** — 商容諫阻選美女
> 商容向紂王進諫，勸阻其選拔美女入宮，以免失民望。

**B** — 紂王聽從費仲建議
> 紂王因思念女媧而煩悶，聽從費仲建議，決定向四路諸侯徵召美女。

LABEL: B causes A

#### PAIR P27

**A** — 盤古開天闢地
> 盤古在混沌初分時開天闢地。

**B** — 神農治世
> 神農嘗百草以治世。

LABEL: A precedes B

#### PAIR P28

**A** — 紂王宣旨征討蘇護
> 紂王因蘇護題詩而大怒，下旨命崇侯虎與姬昌分別征討蘇護。

**B** — 紂王宣召蘇護
> 紂王召見蘇護，意欲選其女入宮為妃。

LABEL: B precedes A

#### PAIR P29

**A** — 紂王即位
> 帝乙去世後，由聞仲輔佐，立壽王為天子，即紂王，定都朝歌。

**B** — 紂王在女媧宮作詩
> 紂王在女媧宮行宮的粉壁上作詩褻瀆女媧。

LABEL: A precedes B

#### PAIR P30

**A** — 神農治世
> 神農嘗百草以治世。

**B** — 禹王治水
> 禹王治理洪災，平定水患。

LABEL: A precedes B

#### PAIR P31

**A** — 帝乙崩
> 帝乙在位三十年後去世。

**B** — 帝乙生三子
> 帝乙在御園遊玩時生下三個兒子：微子啟、微子衍和壽王。

LABEL: B precedes A

#### PAIR P32

**A** — 燧人取火
> 燧人取火，使人類免於生食。

**B** — 盤古開天闢地
> 盤古在混沌初分時開天闢地。

LABEL: B precedes A
