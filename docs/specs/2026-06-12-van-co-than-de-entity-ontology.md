# Entity Ontology chuẩn — Vạn Cổ Thần Đế (万古神帝)

> **Trạng thái:** REFERENCE / DESIGN — chưa đụng data. Plan sửa seed + extraction sẽ viết riêng.
> **Ngày:** 2026-06-12
> **Phạm vi:** Bộ profile entity (kind + attribute) + quan hệ KG tối ưu cho riêng bộ truyện này,
> ráp thẳng vào schema data-driven hiện có (`entity_kinds` + `attribute_definitions`, có `genre_tags` / `auto_fill_prompt`).
> **Genre tag đề xuất:** `xianxia-harem`

---

## 1. Bối cảnh truyện (để ground prompt extraction)

Vạn Cổ Thần Đế là **huyền huyễn lai nhiều tầng**, không thuần "đấm đá":

| Trục | Mô tả | Hệ quả cho ontology |
|---|---|---|
| **Tu luyện / chiến đấu** | Cảnh giới, công pháp, thần thông, thần khí | `character`, `technique`, `item` |
| **Vũ trụ luận / triết học** | Đạo (Thời Gian, Không Gian, Chân Lý, Bản Nguyên, Vận Mệnh), Thiên Đạo, quy tắc | `concept` — **kind đặc trưng nhất** |
| **Hậu cung** | Nhiều nữ chính, đạo lữ, tình địch, hôn ước | `relationship` + edge tình cảm |
| **Chính trị** | Đế quốc, tông môn, thần điện, liên minh & chiến tranh | `organization` + edge phe phái |
| **Báo thù** | Trì Dao giết Trương Nhược Trần → trọng sinh → truy chân tướng | `event` + edge `KILLED` / `BETRAYED` |

Mở màn: Trương Nhược Trần (thái tử Thánh Minh Đế Quốc) bị **vị hôn thê Trì Dao** sát hại → 800 năm sau trọng sinh.
→ Tầng quan hệ (hôn ước, phản bội, tình địch hậu cung) là **load-bearing**, không phải trang trí.

---

## 2. Bộ kind chuẩn — 8 kind

Lai cultivation core + drama, **không** mang theo các kind romance hiện đại (`trope`, `social_setting`, `plot_arc` thuần đời thường).

| # | Code | Nguồn so với seed hiện tại | Vai trò |
|---|---|---|---|
| 1 | `character` | giữ, **trim attr** | Nhân vật |
| 2 | `organization` | giữ | Tông môn / gia tộc / đế quốc / thần điện |
| 3 | `location` | giữ | Thế giới / giới / khu vực / bí cảnh |
| 4 | `concept` | **MỚI** | Đạo / Luật / Nguyên tố / Nguyên lý |
| 5 | `technique` | **đổi tên từ `power_system`** | Công pháp / võ kỹ / bí thuật / thần thông |
| 6 | `item` | giữ | Thần khí / đan dược / bảo vật / trận pháp |
| 7 | `event` | giữ (chỉ event lớn) | Đại sự kiện |
| 8 | `relationship` | giữ, **trim attr** | Cung quan hệ / hậu cung / đạo lữ / tình địch |

**Bỏ khỏi profile này:** `species` (race → string trên character), `terminology` (gộp vào `concept`),
`trope`, `plot_arc`, `social_setting` (meta-văn-học / drama đời thường, không sinh node/edge giá trị).

---

## 2a. Phân tầng theo độ ổn định (glossary vs KG) — nguyên tắc cốt lõi

Trục phân chia **không phải** "ít/nhiều attribute" mà là **độ ổn định của fact theo chương/arc**.
Quan hệ trong VCTĐ đổi liên tục (Trì Dao: *hôn ước → kẻ giết người → kẻ thù → …*) — một attribute tĩnh
ở glossary không biểu diễn nổi "đúng ở arc 1, sai ở arc 5", nó sẽ **rot**. Fact kiểu đó bản chất là
**temporal edge**, phải nằm ở KG kèm dấu chương.

| | Glossary (SSOT authored) | KG (derived, có provenance) |
|---|---|---|
| Lưu gì | **Danh tính bất biến**: name, aliases, kind, race, gender, "nó *là* cái gì" | **Quan hệ + trạng thái đổi theo arc**: liên minh, cảnh giới @chương, status tình cảm |
| Tần suất đổi | gần như không | mỗi arc/chương |
| Extract | 1 lần rồi dedup | mỗi chương emit **delta**, kèm `chapter_id` |

**KG hiện tại đã đủ flexible cho việc này** (xác nhận trong [`KNOWLEDGE_SERVICE_ARCHITECTURE.md`](../03_planning/KNOWLEDGE_SERVICE_ARCHITECTURE.md)):
- Neo4j edge có **temporal properties `valid_from`/`valid_to`** (:38)
- **Provenance edge** `EVIDENCED_BY → ExtractionSource(source_id = chapter_id)` (:479-494)
- **Append-per-chương** + remove-evidence-by-chapter (:514-526) → cập nhật delta không phá data cũ
- **Anchor-node pattern**: surface form từ chương cluster về glossary anchor (:593) → đúng two-layer

> **Cảnh báo:** edge **không có dấu chương** thì sai y như attribute tĩnh. Lợi ích chỉ có nếu mọi
> edge quan hệ/trạng thái đều mang `valid_from`(chương) + `EVIDENCED_BY`. Đây là điều kiện bắt buộc, không tùy chọn.

---

## 3. Attribute — tách 2 tầng (đòn bẩy token)

Nguyên tắc: **chỉ extract field rẻ + dùng để dedup/link KG ở tầng EXTRACT**; mọi field `textarea` dài
đẩy xuống tầng WIKI (sinh on-demand qua `auto_fill_prompt` khi user mở entity, **không** bulk-extract).

> Lý do: `description`/`textarea` × số mention = quả bom token. Character là kind tần suất cao nhất →
> 5 attr extract thay vì 13 giảm ~60% output token mà không mất node/edge nào.

Ký hiệu: `*` = required (mồi dedup) · `[E]` = tầng Extract · `[W]` = tầng Wiki · `field_type`.

### 3.1 `character`
| code | tầng | field_type | ghi chú |
|---|---|---|---|
| `name`* | E | text | |
| `aliases` | E | tags | "Cửu Đế Tử", đạo hiệu… — cực quan trọng cho dedup |
| `gender` | E | text | **giữ ở Extract** — cần cho tracking hậu cung |
| `race` | E | text | **MỚI** — "Long tộc"… string, KHÔNG làm kind |
| `core_drive` | W | text | **MỚI** — 1 câu lý tưởng cốt lõi bất biến ("truy chân tướng, vượt thiên mệnh"); mồi cho dimension động cơ (§3.4 `drive` + edge `PURSUES`). Động cơ *đổi theo arc* sống ở KG, không ở đây. |
| `appearance` | W | textarea | |
| `personality` | W | textarea | |
| `narrative_role` | W | text | chính/phản/phụ; map từ `role` cũ |
| `description` | W | textarea | |

> **MUTABLE → KG, KHÔNG để ở glossary** (sửa so với draft đầu):
> - `affiliation` — nhân vật phản bội / đổi tông. Chỉ dùng làm **mồi cho edge `MEMBER_OF` lần đầu**;
>   truth là edge `MEMBER_OF @valid_from(chương)`, không phải string tĩnh.
> - `cultivation_realm` — lên cảnh giới liên tục → **KG fact** `HAS_REALM @chương`. Bỏ khỏi glossary extract.
>   *(Tùy chọn denormalize `latest_realm` làm cache RAG, nhưng SSOT là timeline ở KG.)*
>
> Bỏ hẳn (romance hiện đại): `occupation`, `social_class`, `emotional_wound`, `love_language`.

### 3.2 `organization`
| code | tầng | field_type | ghi chú |
|---|---|---|---|
| `name`* | E | text | |
| `aliases` | E | tags | |
| `type` | E | text | options: `clan` `sect` `empire` `temple` `faction` |
| `leader` | E | text | mồi edge `LEADS` |
| `headquarters` | W | text | |
| `members` | — | — | **KHÔNG extract** — derive từ edge `MEMBER_OF` |
| `description` | W | textarea | |

### 3.3 `location`
| code | tầng | field_type | ghi chú |
|---|---|---|---|
| `name`* | E | text | |
| `aliases` | E | tags | |
| `type` | E | text | options: `world` `realm` `region` `city` `mountain` `secret_realm` |
| `parent_location` | E | text | mồi edge `PART_OF` |
| `atmosphere` | W | textarea | |
| `significance` | W | textarea | |
| `description` | W | textarea | |

### 3.4 `concept` *(MỚI — kind đặc trưng VCTĐ; gồm cả Đạo lẫn Lý tưởng)*
| code | tầng | field_type | ghi chú |
|---|---|---|---|
| `name`* | E | text | "Không Gian Đạo", "Chân Lý", "Trường Sinh"… |
| `aliases` | E | tags | |
| `category` | E | text | options: `dao` `law` `element` `principle` **`drive`** |
| `definition` | W | textarea | |
| `description` | W | textarea | |

> Mất `concept` là mất toàn bộ tầng triết học/vũ trụ luận của truyện. Đây là kind có giá trị truy xuất cao nhất
> sau `character` (vd. `Trương Nhược Trần --COMPREHENDS--> Không Gian Đạo`).

**`category=drive` — DIMENSION ĐỘNG CƠ (first-class, cho MỌI nhân vật).**
Đặc sản VCTĐ: *mỗi nhân vật — kể cả phụ — đều có động cơ riêng dẫn dắt hành động*; và động cơ tiến hoá theo arc.
**Cố ý dùng `drive` chứ không phải `ideal`**: động cơ trải từ lý tưởng cao (`transcendence`) xuống dục vọng thô
(`bloodlust`, `hedonism`) — nhãn "lý tưởng" loại trừ mất tầng thấp, mà tầng thấp lại là động cơ của *phần lớn*
ma đầu / tà tu / phàm nhân / nhân vật phụ. Dùng **vocab nhỏ động cơ dùng chung** làm `concept` node:

```
godhood · immortality · seek_dao · revenge · protect · transcendence · bloodlust · survival · hedonism …  (~16 node)
```

- Nhân vật **phụ** cũng chỉ tốn **1 edge `PURSUES`** tới drive-concept có sẵn → rẻ ngang main, KHÔNG node-per-character.
  Đây là điều khiến "ai cũng có lý tưởng" rẻ để model toàn bộ cast, không chỉ nhân vật chính.
- Giá trị RAG: cluster ("ai đang truy cầu trường sinh") + truy được **thời điểm đổi mục đích** qua temporal edge (§4).
- **Báo thù chỉ là 1 instance đặc biệt** của dimension này: bất thường vì nó *concrete + trỏ target cụ thể*.
  Model bằng compose, không field thừa: `PURSUES→revenge(concept) @chương` + `BETRAYED←Trì Dao` (§4).
  Đa số lý tưởng khác (trường sinh, chứng đạo) thì **abstract, không target** — đó là dạng phổ biến.

**Seed vocab `drive` cho VCTĐ — CHỐT: tập cố định, tác giả tự thêm sau khi cần, KHÔNG cho extractor tự sinh**
(extractor chỉ được *gán* nhân vật vào drive có sẵn; gặp động cơ lạ → đẩy vào triage như kind `unknown`).

> **Convention code:** mọi `code` (kind / attribute / drive value) dùng **English snake_case** cho dễ tương thích;
> chỉ phần *label / display* giữ Tiếng Việt.

| code | lý tưởng (label) | trục | target? | archetype mang |
|---|---|---|---|---|
| `godhood` | Chứng đạo Thần Đế (đỉnh phong) | cá nhân | abstract | thiên tài đỉnh cao, main |
| `immortality` | Trường sinh, thoát tử vong | cá nhân | abstract | lão quái, cường giả sợ chết |
| `seek_dao` | Cầu/chứng đại đạo, lĩnh ngộ chân lý | cá nhân | abstract → `concept:dao` | tu sĩ cầu đạo |
| `seize_treasure` | Đoạt bảo vật / cơ duyên / tài nguyên | cá nhân | target (item/location) | thợ săn bảo, phản diện tham |
| `revenge` | Báo thù | quan hệ | **target** (char/event) | main (mở màn), khổ chủ |
| `protect` | Thủ hộ / bảo vệ tông môn, người thân | quan hệ | target (char/org/location) | trung nghĩa, hộ đạo |
| `love` | Vì ý trung nhân | quan hệ | target (char) | nữ chính, si tình |
| `restore_clan` | Phục hưng gia tộc / huyết mạch suy tàn | quan hệ | target (org) | hậu duệ gia tộc sa sút |
| `domination` | Quyền lực, xưng bá, thống trị | vũ trụ | có thể target (org/location) | bá chủ, ma đầu, hôn quân |
| `uncover_truth` | Truy chân tướng / âm mưu / nguồn gốc thần linh | vũ trụ | abstract | main (về sau), người tìm sự thật |
| `transcendence` | Siêu thoát, thoát khống chế Thiên Đạo, phá vận mệnh | vũ trụ | abstract | cường giả tối cao, main cuối truyện |
| `usurp_heaven` | Đoạt / khống chế Thiên Đạo, thành chủ tể | vũ trụ | abstract | phản diện tối thượng |
| `survival` | Sinh tồn, chỉ muốn sống sót | bản năng | abstract | phàm nhân, kẻ yếu, kẻ chạy trốn |
| `hedonism` | Hưởng lạc, thỏa mãn dục vọng (sắc, khoái lạc) | bản năng | abstract | dâm ma, kẻ phóng đãng, hôn quân |
| `bloodlust` | Khát máu, giết chóc | bản năng | abstract (đôi khi target) | ma đầu, tà tu, sát nhân điên |
| `freedom` | Tự do, thoát kiềm tỏa / nô dịch | bản năng | target (org/char áp chế) | nô lệ, kẻ bị giam, ma vật phong ấn |

> **Trục `bản năng`** là cái 12 lý tưởng "cao đẹp" ban đầu bỏ sót — nhưng lại là động cơ của *phần lớn* cast phụ
> và phản diện. `survival` đặc biệt phổ biến (phàm nhân, kẻ yếu). Đây là lý do category là `drive`, không phải `ideal`.

> **Arc động cơ của main = chuỗi temporal `PURSUES`**: `revenge` (mở màn) → `seek_dao`/`uncover_truth` (giữa) →
> `transcendence` (cuối). Đây chính là lý do `PURSUES` phải temporal (§4) — nó *là* bản đồ trưởng thành của nhân vật.

### 3.5 `technique` *(repurpose `power_system`)*
| code | tầng | field_type | ghi chú |
|---|---|---|---|
| `name`* | E | text | |
| `aliases` | E | tags | |
| `type` | E | text | options: `cultivation` `martial_art` `secret_art` `divine_power` |
| `rank` | E | text | phẩm/giai nếu có |
| `user` | W | text | derive được từ edge `PRACTICES` |
| `effects` | W | textarea | |
| `description` | W | textarea | |

### 3.6 `item`
| code | tầng | field_type | ghi chú |
|---|---|---|---|
| `name`* | E | text | |
| `aliases` | E | tags | |
| `type` | E | text | options: `weapon` `artifact` `pill` `treasure` `formation` |
| `owner` | W | text | derive từ edge `WIELDS` |
| `symbolic_meaning` | W | textarea | |
| `description` | W | textarea | |

### 3.7 `event` *(chỉ đại sự kiện)*
| code | tầng | field_type | ghi chú |
|---|---|---|---|
| `name`* | E | text | "Trì Dao sát hại Trương Nhược Trần" |
| `participants` | E | tags | mồi edge `PARTICIPATED_IN` |
| `location` | E | text | mồi edge `LOCATED_IN` |
| `event_type` | E | text | `battle` `betrayal` `breakthrough` `death` `political` |
| `date_in_story` | W | text | mốc tương đối ("800 năm trước") |
| `outcome` | W | textarea | |
| `description` | W | textarea | |

### 3.8 `relationship` *(hậu cung / drama — STUB, không entity-hoá đầy đủ)*

> **Sửa so với draft đầu:** core attribute của một cung quan hệ (`status`, `key_conflict`) đổi mỗi arc →
> không được làm attribute tĩnh ở glossary. Glossary chỉ giữ **stub bất biến** làm hook cho wiki article;
> toàn bộ arc *dựng lại từ edge KG có dấu chương* (§4), không lưu tĩnh.

| code | tầng | field_type | ghi chú |
|---|---|---|---|
| `name`* | E | text | "Trương Nhược Trần ↔ Trì Dao" — bất biến |
| `parties` | E | tags | 2+ character — bất biến; mồi cho edge tình cảm |

| ~~`relationship_type` / `status` / `tropes` / `dynamic` / `key_conflict` / `turning_points` / `resolution`~~ | — | — | **KHÔNG ở glossary** → KG temporal edge + wiki-time reconstruct |

> Vì sao vẫn giữ stub thay vì bỏ hẳn kind: một cung quan hệ nổi tiếng (Trương Nhược Trần–Trì Dao) đáng có
> **một wiki article + một anchor ổn định** cho RAG. Nhưng *body* article sinh từ lịch sử edge KG, không phải
> từ attribute tĩnh. Stub = identity; KG = câu chuyện. Nếu sau này thấy stub thừa, demote tiếp thành KG-only.

---

## 4. Quan hệ KG (tầng `knowledge-service`)

KG build ở `knowledge-service`, mỗi node neo về glossary qua `glossary_entity_id` FK (two-layer pattern).
~18 edge, gồm cả trục hậu cung/drama:

### Character → Character
```
MASTER_OF · DISCIPLE_OF · FAMILY_OF
LOVER_OF · BETROTHED_TO · DAO_COMPANION_OF      ← trục hậu cung
RIVAL_OF · ENEMY_OF · ALLY_OF                    ← tình địch / phe
KILLED · BETRAYED · SAVED                        ← trục báo thù (mở màn truyện)
```
### Character → khác
```
MEMBER_OF (org) · COMPREHENDS (concept:dao/law) · PRACTICES (technique)
WIELDS (item) · PARTICIPATED_IN (event) · FROM (location)
PURSUES / DRIVEN_BY (concept:drive | target cụ thể)   ← dimension động cơ, MỌI nhân vật, TEMPORAL
```
> `PURSUES` là edge **temporal** (`valid_from`/`valid_to` theo chương) — đây là chỗ bắt được "main đổi mục đích":
> đóng `PURSUES→revenge` rồi mở `PURSUES→seek_dao`. Phân biệt với `COMPREHENDS` (lĩnh ngộ Đạo) — khác động từ, khác category concept.
### Org / Location
```
SUBORDINATE_OF · ALLIED_WITH · AT_WAR_WITH   (org↔org)
PART_OF                                        (location↔location)
```
### Relationship-entity
```
relationship --INVOLVES--> character   (nối entity quan hệ với các bên)
```

> **Mọi edge ở nhóm "đổi theo arc" (tình cảm, phe phái, cảnh giới) BẮT BUỘC mang `valid_from`(chương) +**
> **`EVIDENCED_BY → ExtractionSource(chapter_id)`.** Edge không dấu chương = sai như attribute tĩnh.
> Edge bất biến (`MASTER_OF`, `FAMILY_OF`, `PART_OF`, `COMPREHENDS`) thì không cần khoảng chương.
>
> Lưu ý dedup: `character.affiliation`/`cultivation_realm` (string) chỉ là **mồi** sinh edge lần đầu;
> truth là edge temporal. `organization.members`, `technique.user`, `item.owner` KHÔNG extract — derive ngược từ edge.

---

## 5. KHÔNG extract thành entity (anti-pattern)

| Cám dỗ | Đúng ra là |
|---|---|
| `Bloodline` entity | string/edge: `character --HAS_BLOODLINE--> "Thanh Long Huyết Mạch"` |
| `Constitution` entity | `character.special_constitution` (string, có thể gộp vào `race`/wiki) |
| `RealmRank` / mỗi cảnh giới một node | `character.cultivation_realm` (string); ladder = 1 `concept` |
| Mỗi `species` một kind | `character.race` (string), promote sau nếu bị query nhiều |
| Tất cả công pháp lặt vặt | chỉ technique có tên riêng + ý nghĩa cốt truyện |
| `Goal`/`Motivation` entity kind riêng cho mỗi nhân vật | `concept:drive` (vocab dùng chung) + edge `PURSUES` temporal — 1 edge/nhân vật |
| "Báo thù" làm theme/trope | 1 instance của dimension động cơ: `PURSUES→revenge` + `BETRAYED` edge |

---

## 6. Ngân sách node mong muốn (KG cho RAG)

Tỷ lệ tối ưu giá-trị/token cho bộ này (đã tính trọng số hậu cung/drama):

```
38% character
17% organization
13% location
12% concept           ← cao bất thường so với xianxia thường, vì tầng triết học VCTĐ
 8% relationship      ← cao bất thường, vì hậu cung/drama
 6% event
 6% technique + item
```

---

## 7. Map về data hiện tại (cho plan sau, KHÔNG làm ở đây)

Profile này ráp gần như 1-1 vào schema sẵn có → plan sửa data rẻ:

- **Tái dùng nguyên:** `character`, `organization`, `location`, `item`, `event`, `relationship` (chỉ thêm `genre_tags`, set tầng E/W qua `is_required` + `auto_fill_prompt`).
- **Đổi tên:** `power_system` → `technique` (giữ attr; type options đổi).
- **Thêm mới:** kind `concept` + 5 attr; 2 attr `character.race`, `character.cultivation_realm`.
- **Genre-filter extraction:** prompt extraction lọc kind theo `genre_tags` của book = `xianxia-harem` → kind romance đời thường không bao giờ vào prompt.

### Pipeline extraction (theo phân tầng §2a)

```
Pass A — mỗi chương (RẺ, ~95% corpus, chạy ở knowledge-service worker-ai):
   • detect mention → link vào glossary anchor sẵn có (chủ yếu dedup)
   • emit edge/state-DELTA của chương → KG, kèm valid_from(chương) + EVIDENCED_BY(chapter_id)
   • KHÔNG re-extract attribute ổn định mỗi chương
Pass B — mỗi entity MỚI (1 lần): fill danh tính bất biến (tầng E §3) → glossary qua /extract-entities
Pass C — on-demand: sinh wiki (tầng W) từ glossary anchor + lịch sử edge KG
```

### Việc cần plan riêng (mở)
1. Seed `xianxia-harem` profile vào `DefaultKinds` (`services/glossary-service/internal/domain/kinds.go`) — chỉ tầng-E attr.
2. Lọc kind theo `genre_tags` trong extraction handler.
3. Viết `auto_fill_prompt` cho các attr tầng Wiki (Pass C).
4. Định nghĩa edge set ở `knowledge-service` (§4) — **bao gồm `valid_from`/`EVIDENCED_BY` cho edge mutable** + mapping mồi string → edge.
5. Pass A delta-extraction: cơ chế emit "thay đổi quan hệ/cảnh giới @chương" thay vì re-extract full.
6. **Mở:** xác nhận "2 bước extraction" của bạn ↔ Pass A/B ở trên? Nếu (B1) detect name+kind → (B2) fill attr,
   thì B2 = tầng-E (§3) cho entity mới, còn relationship/state delta đi đường Pass A.
