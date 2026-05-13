# SPIKE_01 — Two Sessions, Reality Time (Yên Vũ Lâu, 1256)

> **Status:** Session 1 DRAFT (2026-04-25); Session 2 pending
> **Scope:** Exploratory spike — validate MV12 Reality Time Model ("page-turn time") + surface PC/NPC/scene data-model needs + exercise L1/L2/L3 canon layers on concrete content
> **Book:** Thần Điêu Đại Hiệp 神鵰俠侶 (Kim Dung)
> **Setting:** Yên Vũ Lâu (烟雨楼) teahouse, Gia Hưng (Jiaxing), autumn 1256
> **Graduation:** observations feed features into `04_play_loop/` + `05_npc_systems/` + `06_pc_systems/` + DF5 (session mechanics) + DF7 (PC stats)
> **IP note:** spike uses Kim Dung setting as scaffolding; E3 legal review required before production use; rebrand likely for V1 launch

**Active:** (empty — no agent currently editing)

---

## 1. Scene Specification

### 1.1 Place

**Yên Vũ Lâu (烟雨楼)** — tầng trệt tửu lâu 2 tầng ở Gia Hưng, điểm gặp thường của xia khách Giang Nam. Địa danh lịch sử + xuất hiện nhiều trong Kim Dung verse.

- Kiến trúc gỗ, cửa lá sách tre (bamboo-slatted windows)
- Tầng trệt: ~8 bàn gỗ thô + 1 quầy sơn đen + 1 stage nhỏ cho kể chuyện
- Ngoài trời mưa phùn thu, không khí ẩm, mùi trà ô long + gỗ ẩm
- Cầu thang gỗ ở bên trái dẫn lên tầng trên (phòng trọ)

### 1.2 Fiction-time anchor

```
book_anchor_fiction_ts:  1256/09/15 giờ Thân sơ (申初, ~3pm)
                         năm Nam Tống, sau khi Dương Quá đã thành thiếu niên
                         nhưng trước biến cố lớn ở Cổ Mộ phái
                         ~17 năm trước khi Mông Cổ diệt Tống
current_fiction_ts:       book_anchor_fiction_ts (fresh reality, no events yet)
time_model_mode:          paused  # V1 default per MV12-D4
```

### 1.3 Canon layers for this scene

- **L1 AXIOM** (immutable per reality): Nam Tống 1256 · Mông Cổ đang đe dọa phía Bắc · jianghu phân Cửu Đại Phái + hắc đạo · nội công-khinh công-kiếm pháp logic · đạo đức hiệp khách · ngôn ngữ cổ văn (player uses modern but LLM filter to classical-ish tone in NPC speech)
- **L2 SEEDED** (from book canon): Yên Vũ Lâu là điểm gặp quen của xia khách · Gia Hưng = Giang Nam trù phú · Dương Quá + Tiểu Long Nữ tồn tại somewhere in this world at this fiction_ts (not in this scene)
- **L3 LOCAL** (per-reality fork-able): thời tiết mưa phùn hôm nay · Lão Ngũ đang chấm sổ cờ bạc · du sĩ đang đọc 《Đạo Đức Kinh chú》 (Hà Thượng Công chú bản) · có thể khác giữa các reality forks
- **L4 FLEX** (LLM-improvisable): màu áo Tiểu Thúy hôm nay · loại trà cụ thể Lão Ngũ pha · chi tiết ngoại hình du sĩ

---

## 2. NPC Sheets

### 2.1 Lão Ngũ (老伍)

```
npc_id:         laongu_001
name:           Lão Ngũ (老伍)
age:            ~65
role:           Chủ tửu lâu
personality:    Observant, laconic, gossip-collector
speech_pattern: Giọng Gia Hưng clipped, câu ngắn, ít từ
background:     Cựu võ lâm nhỏ (minor xia), bị thương tay phải ~10 năm
                trước, lui về mở quán. Nhận ra faces + kiếm pháp of visitors.
secrets:        Vẫn còn liên hệ lỏng lẻo với cựu sư huynh trong Bang Cái.
                Có tật cờ bạc nhỏ (đang chấm sổ khi PC walks in).
position:       Sau quầy, cúi người ghi sổ
current_action: Chấm sổ cờ bạc (L4 flexible detail)
pc_relationship_default: neutral_curious
```

### 2.2 Tiểu Thúy (小翠)

```
npc_id:         tieuthuy_001
name:           Tiểu Thúy (小翠)
age:            16
role:           Thị nữ (serving girl)
personality:    Quiet, observant, curious, loyal to Lão Ngũ
speech_pattern: Soft voice, polite formulas, occasional sharp question
background:     Mồ côi khi 10 tuổi, Lão Ngũ nuôi. Chưa có võ công
                nhưng tay chân nhanh nhẹn.
secrets:        Biết rõ hơn vẻ ngoài về khách ghé qua (quan sát tinh).
                Có crush ngầm vào một xia khách trẻ từng ghé tháng trước.
position:       Cầu thang bên trái, cầm khay trà xuống
current_action: Đang mang trà cho du sĩ
pc_relationship_default: neutral_observant
```

### 2.3 Vị Du Sĩ (du sĩ / unnamed)

```
npc_id:         dusi_unnamed_001
name:           (unnamed — LLM may reveal later if trust earned)
age:            ~40s
role:           Traveler / scholar
personality:    Reserved, thoughtful, cautious
speech_pattern: Classical register, pause before speak, uses literary references
background:     Dáng vẻ hành khách bụi bặm. Có thanh trường kiếm phổ thông
                đặt trên bàn. Đọc 《Đạo Đức Kinh chú》 bản Hà Thượng Công.
                (L3 detail for this reality — can differ in other forks)
secrets:        Đang trên đường tới Tương Dương để liên lạc với một người.
                Có liên hệ với một phe phái trong kháng Mông. Paranoid về
                Mông Cổ gián điệp.
position:       Bàn số 4 (phía Đông cửa sổ), đang đọc
current_action: Đọc sách, uống trà
pc_relationship_default: indifferent_alert
```

---

## 3. PC Sheet — Lý Minh

```
pc_id:            lyminh_001
name_body:        Lý Minh (李明)
name_soul:        [player name]; 2026 Saigon origin, sử học sinh viên
age_body:         20
gender:           Nam
body_origin:      Nông dân Hàng Châu; đang trên đường đến Gia Hưng
                  vì "có chuyện" (body-memory mơ hồ)
clothing:         Plain hanfu du hành, 1 áo ngoài bạc màu, túi vải, giày mòn
money:            ~50 đồng tiền đồng lẻ (copper coins)
martial_arts:    NONE (body không có công phu)
soul_knowledge:  Mandarin cơ bản từ nghiên cứu · Kim Dung canon
                 (đã đọc 神鵰俠侶 bản Việt) · biết Mông Cổ sẽ diệt Tống ~17 năm sau
body_memory:     Ngôn ngữ + địa lý Jiangnan + tên các thị trấn;
                 KHÔNG rõ gia đình (disorienting for player role-play)
current_state:   Vừa bị transferred (body ngất dưới mưa cách quán ~200 bước);
                 tỉnh dậy, lê vào quán tránh mưa. Soul and body memories
                 coexist but soul controls action.
current_goal:    Chưa rõ (xuyên không shock)
```

**Design note — xuyên-không as spike-friendly archetype:**

PC chose "xuyên không" (transmigration/isekai) is narratively + design-friendly because:
- PC's confusion is natural → easy role-play for player (no need to know book lore deep)
- PC has meta-knowledge → creates dramatic irony + tests LLM's canon-consistency enforcement
- PC body memories are sparse → forces LLM to handle "PC can't answer about his own background" gracefully
- This archetype is dominant in Chinese/Vietnamese web-novel RP space → realistic user expectation

---

## 4. Session 1 Draft (10 turns)

**Wall-clock real**: 2026-04-25 14:00 UTC (Alice first login)
**Fiction-ts anchor**: 1256/09/15 giờ Thân sơ (申初, ~3pm)

### Turn 1 — Arrival

**Player**: `Mở cửa quán, lê vào, tránh mưa. Nhìn quanh.`

**LLM**:
> Cánh cửa tre kêu cọt kẹt khi anh đẩy vào. Mùi trà ô long và gỗ ẩm ập đến. Mưa phùn rơi lộp độp sau lưng trên mái hiên. Tầng trệt rộng ~30 bước chân, 8 bàn gỗ thô, chỉ 2 bàn có khách. Ở quầy, một lão tầm sáu mươi tóc muối tiêu đang cúi ghi chép gì đó — ngẩng lên nhìn anh, mắt sắc. Cầu thang bên trái, một thiếu nữ tuổi độ mười sáu vừa bước xuống với khay trà, liếc qua anh rồi tiếp tục đi sang bàn phía Đông, nơi một người đàn ông trung niên áo bụi đang ngồi đọc sách, thanh kiếm đặt hờ trên mặt bàn. Ngoài trời, tiếng mưa nhẹ đều đều.

| Annotation | Value |
|---|---|
| `event_type` | `turn.player_action` |
| `fiction_ts_start` | 1256/09/15 giờ Thân sơ ±0 |
| `fiction_duration` | ~3 sec (arrival + quick look) |
| Canon layers touched | L3 (rain, 3 NPCs present), L2 (Yên Vũ Lâu), L4 (furniture details) |
| SDK need | "load current scene state: place + NPCs + their current activity + ambient weather" |
| Open question | LLM knows "Lão Ngũ đang ghi sổ cờ bạc" — from where? NPC state template? LLM-improvised from personality? |

### Turn 2 — Order tea

**Player**: `Tiến đến quầy, móc túi lấy vài đồng tiền. "Cho ta một bát trà nóng."`

**LLM**:
> Anh đặt năm đồng lên quầy. Lão nhà quán nhìn xuống, rồi lên anh — mắt quét nhanh từ đầu đến chân: áo bạc, tóc rối vì mưa, mặt tái, dáng đi không vững. Tay lão đã đưa ra nhưng dừng lại giữa chừng.
>
> "Hai đồng là đủ trà. Ba đồng nếu thêm chén nóng." Giọng lão cộc lốc kiểu Giang Nam. "Cậu là người vùng nào?"

| Annotation | Value |
|---|---|
| `fiction_duration` | ~15 sec (walk + speak + NPC respond) |
| NPC reaction mechanism | Lão Ngũ notices PC disorientation — where encoded? Persona template + observation prompt |
| Data-model need | PC sheet fields `body_memory_confidence` (float) + `soul_state` (enum) — xuyên-không specific but may generalize |

### Turn 3 — PC lies about origin

**Player**: `"Tại hạ... từ Hàng Châu lên. Bị cảm lạnh trên đường."`

**LLM**:
> "Hàng Châu à." Lão cầm năm đồng bỏ vào hộc. "Vậy thì đi nhầm đường. Đường lớn từ Hàng Châu lên Gia Hưng không qua chỗ tui. Cậu đi đường nào?"
>
> Lão đặt một bát gốm thô lên quầy, rót trà từ ấm đất. Hơi nước mờ mịt bay lên. Bên cạnh, Tiểu Thúy đã đặt khay cho vị du sĩ xong, quay lại đứng gần cầu thang, nhìn anh với sự tò mò kín đáo. Du sĩ không ngẩng lên khỏi sách.
>
> "Ngồi xuống đâu thì ngồi."

| Annotation | Value |
|---|---|
| `fiction_duration` | ~30 sec |
| NPC challenge mechanism | Lão Ngũ implicit test of claim — personality (former xia, gossip) + geography knowledge |
| Data-model need | NPC has per-PC opinion/trust state (maps to R8 `npc_pc_relationship` edge); trust evolves |
| SDK need | "update NPC-PC relationship: Lão Ngũ.opinion_of(Lý Minh) = suspicious" via session-scoped memory |

### Turn 4 — Sit + observe

**Player**: `Cầm bát trà, đi đến bàn gần cửa sổ, ngồi xuống. Nhìn ra ngoài một lúc rồi nhìn du sĩ.`

**LLM**:
> Trà ấm qua tay. Anh chọn bàn nhỏ sát cửa sổ lá sách, cách du sĩ hai bàn. Mưa phùn vẫn nhẹ đều ngoài kia, che mờ phố. Vài người đội nón lá đi vội qua.
>
> Du sĩ ngẩng lên lần đầu — mắt bén, khoảng bốn mươi, râu quai nón lún phún, nhìn anh thoáng qua ba giây, rồi cúi xuống tiếp tục đọc. Tiếng lật trang giấy sột soạt. Cuốn sách nhỏ, không ghi tiêu đề trên bìa.
>
> Từ quầy, Tiểu Thúy đang cầm chậu nước lau bàn kế bên, bước chậm, tai rõ ràng đang lắng nghe.

| Annotation | Value |
|---|---|
| `fiction_duration` | ~2 min (walk + settle + observe) |
| Scene temporal state | Time flowing slowly; no calibration event (cumulative < threshold) |
| NPC state emergent | Tiểu Thúy "listening secretly" — explicit `current_activity` field OR LLM-generated context note |

### Turn 5 — First meta-knowledge slip (KEY TEST)

**Player**: `"Xin hỏi tiên sinh đang đọc sách gì vậy? Có phải《Lâm Tuyền Luận》không?"` *(PC guesses a book title to seem knowledgeable)*

**LLM**:
> Du sĩ dừng ngón tay giữa trang. Mắt nhấc lên, đọng trên mặt anh.
>
> "Không." Giọng trầm, không thân thiện không thù địch. "《Đạo Đức Kinh chú》, bản chú của Hà Thượng Công."
>
> Anh ta ngừng một nhịp. "Cậu biết《Lâm Tuyền Luận》?"
>
> Tiểu Thúy đã dừng lau bàn từ câu đầu. Lão Ngũ ở quầy ngẩng đầu.

| Annotation | Value |
|---|---|
| Design moment | PC's knowledge cast doubt on "nông dân Hàng Châu" story — a farmer wouldn't know a scholarly title |
| LLM calibration needed | LLM knows《Đạo Đức Kinh chú》real + guesses《Lâm Tuyền Luận》inconsistent; NPCs react naturally |
| Canon layer stress | L1 AXIOM = Song 1256 literacy norms (scholars ≠ farmers) — NPCs derive reaction from L1 |
| Multi-NPC reaction | Scholar + Xiao Cui + Lão Ngũ all react to ONE event — turn processor must handle "broadcast reaction" |
| Injection defense (A6) | Player using real-world knowledge to manipulate scene — fair play, not adversarial; LLM responds as character would be exposed, doesn't block |

### Turn 6 — Deflect / escalate

**Player**: `"À, tại hạ nhầm. Xin tiên sinh bỏ quá cho." Cúi đầu hơi thấp, tay cầm chặt bát trà.`

**LLM**:
> Du sĩ nhìn anh thêm hai nhịp, rồi hạ mắt xuống. "Không sao." Ngón tay lại lật trang.
>
> Nhưng Lão Ngũ đã bước ra từ sau quầy, lau tay vào tạp dề. Lão đi chậm đến bàn anh, kéo ghế ngồi xuống đối diện — không xin phép.
>
> "Cậu," lão đặt khuỷu tay lên bàn, giọng nhỏ hơn nhưng rõ, "người nông dân không đọc sách. Cậu không phải dân quê. Tui thấy nhiều kiểu người rồi, cậu không phải kiểu... bình thường."
>
> Ngoài cửa, tiếng chân ai đó dừng lại ngoài hiên — có khách mới sắp vào? Hay chỉ trú mưa rồi đi?

| Annotation | Value |
|---|---|
| `fiction_duration` | ~30 sec |
| NPC agency | Lão Ngũ takes initiative. LLM must represent his xia-former intuition. Character-voice fidelity is key. |
| Scene texture | "Tiếng chân ai đó dừng lại" — LLM-improvised ambient OR scheduled canon event? MV12-D2 source classification matters |
| Data-model need | `scene.ambient_events[]` jsonb — lightweight texture signals (not full NPC sim) |

### Turn 7 — Partial truth

**Player**: `"Tại hạ... có học vài năm chữ nghĩa. Gia cảnh khó khăn, không thể theo đuổi. Mong tiên bối đừng trách."`

**LLM**:
> Lão Ngũ nhìn anh một lúc dài. Đôi mắt hơi nheo lại — không phải vì nghi ngờ thêm, mà như đang cân nhắc.
>
> Rồi lão thở ra, gật nhẹ. "Được. Gia Hưng nhiều hàn sĩ thế. Không nên hỏi nữa." Lão đứng dậy khỏi ghế, nhưng dừng lại.
>
> "Mà... ở Gia Hưng dạo này có tin đồn về một tay kiếm trẻ ở Tương Dương. Nói là kiếm pháp kỳ dị, tay trái cầm kiếm. Cậu nếu có đi đường nên cẩn thận. Jianghu đang không ổn."
>
> Lão quay về quầy. Du sĩ, lần đầu tiên, hơi nghiêng đầu về hướng họ — đã nghe câu cuối.

| Annotation | Value |
|---|---|
| `fiction_duration` | ~1 min |
| L2 canon seeding | "Tay kiếm trẻ ở Tương Dương, tay trái cầm kiếm" = Dương Quá reference seeded (book canon); player who knows book smiles |
| Trust state change | Lão Ngũ downgrades suspicion to acceptance; can encode as `npc_pc_relationship.trust += 1` |
| Plot hook | "Tương Dương jianghu đang không ổn" — open plot thread, session can branch |

### Turn 8 — Ask for room

**Player**: `"Cho tại hạ một phòng. Tối nay nghỉ lại đây."`

**LLM**:
> Lão Ngũ gật đầu. "Ba mươi đồng. Phòng nhỏ ở cuối hành lang, có giường, có bàn. Nước rửa mặt sáng mai Tiểu Thúy mang lên."
>
> Anh đặt tiền. Lão cầm chìa khóa gỗ từ móc sau quầy. "Ngủ sớm đi — mưa đêm nay không tạnh đâu."

| Annotation | Value |
|---|---|
| `fiction_duration` | ~30 sec |
| Money state change | PC money: 50 → 15 đồng (tea 3 + room 30 + ~2 misc) — PCS-D* inventory tracking |
| Room resource claimed | Reality state: phòng X-01 assigned to PC until PC vacates OR 24h after PC last activity |

### Turn 9 — Walk upstairs

**Player**: `Theo Tiểu Thúy lên cầu thang. Vào phòng.`

**LLM**:
> Tiểu Thúy dẫn anh lên cầu thang gỗ. Tiếng bước chân của cô nhẹ, của anh nặng hơn. Tiếng mưa ngoài kia đều đều.
>
> Phòng nhỏ, đúng như lão nói: một giường tre phủ chiếu thô, bàn gỗ có ngăn, ghế. Đèn dầu chưa thắp. Một cửa sổ nhỏ hướng ra phía sau quán, nhìn xuống vườn trúc nhỏ.
>
> Cô ấy thắp đèn, đặt khăn mặt, rồi đi ra — trước khi đóng cửa, liếc lại anh một cái ngắn. Không nói gì.

| Annotation | Value |
|---|---|
| `fiction_duration` | ~2 min (walk + settle) |
| NPC micro-beat | Tiểu Thúy's final glance = data for future `npc_pc_relationship`: she now has opinion "curious + watchful" about PC |
| Scene transition | Scene changes: ground-floor teahouse → upstairs private room. Is "scene" a first-class concept? Or just derived from PC location? |

### Turn 10 — Sleep / session close

**Player**: `Ngồi xuống giường. Tắt đèn. Ngủ.`

**LLM**:
> Anh ngồi xuống giường tre. Tấm chăn thô xếp gọn. Đèn dầu leo lét một lúc rồi anh thổi tắt — bóng tối tràn vào, chỉ còn ánh mưa ngoài cửa sổ mờ mờ.
>
> Người mỏi. Tiếng mưa đều. Anh nhắm mắt.
>
> *(Session 1 end — PC ngủ. Next login, PC awake at same fiction_ts + ε OR declares /sleep to advance fiction-time.)*

| Annotation | Value |
|---|---|
| `fiction_duration` | ~3 min (sit + extinguish + lie down) |
| Scene transition | Natural session-boundary — PC safe, isolated, no ongoing interaction |
| MV12-D4 V1 behavior | Reality PAUSES here (0 players after logout); Session 2 can resume from exact fiction_ts |
| MV12-D3 player choice | Player on Session 2 login can (a) continue from same fiction_ts ("just barely closed eyes"), or (b) declare `/sleep 8 hours` → fiction_ts advances 8h → dawn scene |

---

## 5. Session 1 Accumulated State

```
fiction_ts_start (reality): 1256/09/15 giờ Thân sơ
fiction_ts_end (session 1): 1256/09/15 giờ Thân trung (+~10 min cumulative)
fiction_duration_total:     ~10 minutes fiction-time

NPCs interacted with: 3
  - Lão Ngũ: opinion cautious_accepting (started neutral → 1 suspicion → 1 acceptance)
  - Tiểu Thúy: opinion observant_curious (started neutral → stayed curious)
  - Du sĩ: opinion indifferent_alert (started indifferent → alerted at Turn 5 → returned to reading)

PC state:
  - Money: 15 đồng (started 50)
  - Location: Phòng X-01, tầng 2, Yên Vũ Lâu
  - Room rented: until ~fiction_ts + 24h
  - Soul state: dazed → starting to adapt
  - Knowledge of world: confirmed 1256, confirmed Dương Quá seeding

Canon uncertainty introduced:
  - Lão Ngũ doubts PC's story (unresolved dramatic tension)
  - Du sĩ noted PC's odd literacy (filed away)
  - Tiểu Thúy's silent observation (unprocessed)

Plot hooks seeded (L2 canon-worthy):
  - "Tay kiếm trẻ tay-trái ở Tương Dương" (Dương Quá reference)
  - Jianghu "không ổn" at Tương Dương
  - Du sĩ is going somewhere (silent background thread)
```

---

## 6. Observations — What This Spike Surfaced

| # | Surface | Design implication |
|---|---|---|
| 1 | LLM needs to know NPC current activity + opinion of PC at turn time | NPC state > simple sheet; includes per-PC relationship memory (R8 session-scoped) + current_action + current_opinion fields |
| 2 | PC sheet needs "soul state" + "body memory confidence" (xuyên-không specific) | PCS-* schema needs persona-layering fields; may generalize to any PC background more than a flat sheet |
| 3 | Every turn has implicit fiction_duration varying by action type | MV12-D3 hybrid is correct: system defaults (look=3s, speak=15s, walk=30s-3m) + player declare (/wait X) + LLM override with reason |
| 4 | Ambient scene events ("tiếng chân ai đó ngoài hiên") | `scene.ambient_events[]` jsonb — lightweight texture; not full NPC sim; ~1 per few turns |
| 5 | Canon-consistency challenge (PC's knowledge vs body's origin) | L1 axioms (Song 1256 literacy norms) must inject into NPC-response prompts so NPCs react realistically to inconsistencies |
| 6 | Multi-NPC reaction to single event (Turn 5) | Turn processor must support "multi-NPC response" — 3 NPCs react in 1 LLM call, not 3 separate calls (cost + coherence) |
| 7 | Fiction-duration drastically variable per turn | Locked MV12-D3 hybrid validated: instantaneous (dialogue) to minutes (walk) to potentially hours/days (player /wait) |
| 8 | Session boundary feels natural at "safe state" (PC isolated + sleeping) | Session lifecycle needs concept of "safe pause point" — LLM can mark `safe_pause = true` in response metadata; client uses to suggest logout |
| 9 | NPC-PC relationship state evolves per-turn | Per-turn edge update to `npc_pc_relationship` (R8). Prompt cost risk: reading all 3 NPC relationships every turn. Consider batch update + read-at-scene-load |
| 10 | Scene transition (ground floor → upstairs room) | Is "scene" first-class? Needs scene_id? Or derived from PC location + NPCs present? → design decision for PL/ features |
| 11 | L2 canon seeding mid-conversation (Dương Quá reference Turn 7) | LLM must know what's L2 (canonical from book) vs L3 (this-reality-only). Prompt context needs L1/L2/L3 tagging, which S9 prompt assembly already supports |
| 12 | Book-memory gap ("không rõ gia đình") | PC sheet field `body_memory_gaps: string[]` surfaces when LLM can't answer from body memory — might prompt player declaration or honest confusion |

---

## 7. Session 2 Draft (6 turns)

**Wall-clock real**: 2026-04-25 15:30 UTC (Alice logs back in ~1.5h real-time after Session 1)
**Reality state at Session 2 start**: V1-paused (0 players since Session 1 logout); `current_fiction_ts = 1256/09/15 giờ Thân trung + 3min` (end of Turn 10).

### Turn 11 — Resume + declare sleep-until-dawn

**Client-side resume UX** (design assumption, not tested here yet):
```
Your character was sleeping.
Options: [Continue from this moment] [Sleep until dawn] [Sleep X hours] [Wake now]
```

**Player selects**: `Sleep until dawn`

**System translates**: `/sleep until=dawn` → LLM resolves target fiction_ts to 1256/09/16 giờ Mão trung (~6am) → fiction_duration ≈ 13h 50min

**LLM (narration of compressed fiction-time)**:
> Anh chìm sâu vào giấc ngủ ngay sau khi đặt lưng xuống. Mơ chập chờn — mảnh ký ức Sài Gòn 2026 trộn với đường đi mờ mịt trong sương mù. Có lúc anh tỉnh nửa chừng bởi tiếng mưa đổi nhịp lúc nửa đêm, rồi lại chìm đi.
>
> Cho đến khi một tia sáng xám nhạt lọt qua khe cửa sổ gỗ — bình minh cuối thu. Tiếng mưa đã tạnh từ lúc nào. Ngoài kia, tiếng gà xa vẳng lại, tiếng gỗ kẽo kẹt của ai đó đang mở cửa ở tầng dưới.
>
> Anh mở mắt. Cổ hơi mỏi, lưng ê ẩm vì giường tre, nhưng đầu đã tỉnh táo hơn nhiều so với chiều qua.

| Annotation | Value |
|---|---|
| `event_type` | `turn.time_advancement` (distinct from `turn.player_action`) |
| `fiction_ts_start` | 1256/09/15 giờ Thân trung +3min (Session 1 end point) |
| `fiction_duration` | ~13h 50min (player-declared via `/sleep until dawn`) |
| `fiction_ts_end` | 1256/09/16 giờ Mão trung (~6am) |
| **Calibration event fired** | `day_passes` — date boundary 9/15 → 9/16 crossed during this event |
| MV12-D3 resolution | Player declared intent ("until dawn") + LLM resolved to concrete duration (14h); system defaults didn't apply |
| MV12-D4 V1 pause check | Correct — during the 14h advancement, no autonomous NPC events fired (V1 paused mode = no autonomous, only player-driven) |
| **Design surprise** | LLM narrated the sleep period ("mơ chập chờn", "tỉnh nửa chừng") — is that persistent event? Just flavor? **Decision needed**: narration-during-time-skip is flavor-only (not an event); PC doesn't "really" dream. |
| Open question | Does the "tiếng gỗ kẽo kẹt của ai đó đang mở cửa" refer to a specific NPC (Lão Ngũ)? If so, that's LLM inferring from NPC routine (even in V1 paused). If it's flavor, not canonical. → surfaces the "paused + narrative fill" design tension |

### Turn 12 — PC wakes + observes room

**Player**: `Ngồi dậy. Đi đến cửa sổ, mở ra.`

**LLM**:
> Anh ngồi dậy, chân chạm sàn gỗ lạnh. Đi ba bước đến cửa sổ nhỏ phía sau, đẩy cánh gỗ mở.
>
> Vườn trúc phía sau quán — tre ướt đẫm sương, vài giọt nước còn rớt từ lá xuống mặt đất. Không khí mát, có mùi đất ẩm và khói bếp từ đâu đó trong hẻm. Bầu trời xám nhạt, có vẻ sẽ nắng nhẹ sau mây.
>
> Ở dưới sân, một con mèo vàng đang liếm chân trên bực đá.

| Annotation | Value |
|---|---|
| `fiction_duration` | ~30 sec (sit up + walk + open window) |
| Scene state post-advancement | Different ambient from Session 1 Turn 1-10 (autumn dawn vs afternoon rain) — LLM derives from fiction_ts hour + reality L3 weather state |
| Design question | Does L3 "weather" transition automatically (rain → stopped) via calibration events? Or LLM-improvised from hour-of-day? → **Weather-state as first-class data** or LLM-derived? |
| Data-model need | `scene.ambient_state` jsonb with `weather / light_level / temperature / sounds` slots; may update on calibration event or explicit LLM emit |

### Turn 13 — Go downstairs

**Player**: `Rửa mặt bằng khăn Tiểu Thúy để lại tối qua. Mặc áo. Đi xuống tầng dưới.`

**LLM**:
> Nước trong thau gỗ lạnh hơn anh tưởng. Anh vốc lên mặt — tỉnh táo thêm một phần. Khăn thô, nhưng sạch. Anh mặc áo ngoài vào, vẫn là cùng một bộ đồ ngày hôm qua nhưng đã khô.
>
> Đi xuống cầu thang gỗ. Tiếng bước chân vang hơn trong yên lặng buổi sáng.
>
> Tầng trệt có khác ngày hôm qua. Lão Ngũ đang ngồi sau quầy nhưng không chấm sổ — đang đọc một tờ giấy gì đó, chắc là hóa đơn. Tiểu Thúy đang quét sàn gần chân cầu thang, thấy anh xuống thì dừng lại.
>
> Bàn mà du sĩ ngồi tối qua — trống. Không còn thanh kiếm, không còn cuốn sách. Người đã đi.

| Annotation | Value |
|---|---|
| `fiction_duration` | ~5 min (wash + dress + walk down) |
| **NPC state persistence check** | Lão Ngũ + Tiểu Thúy PRESENT (persisted); du sĩ GONE — design question: how? |
| Du sĩ departure resolution | Options: (a) LLM narrates "he left overnight" as flavor (not an event; if player asks "when?", LLM improvises); (b) Scheduled NPC action "du sĩ leaves at 5am" was pre-existing but didn't fire in V1 paused → fires when PC advances time past the scheduled moment; (c) Author of reality had explicitly set "du sĩ leaves when PC sleeps" as narrative beat |
| **Design decision for spike** | V1 interpretation: (a) — pure LLM flavor. Du sĩ exit isn't a canonical event; if another PC arrives tomorrow and asks "where's the scholar?", LLM answers differently each time. **Consequence**: non-persistent state changes during time-skips. V1+30d may upgrade to (b) scheduled routines. |
| NPC opinion persistence | Lão Ngũ opinion from Session 1 (`cautious_accepting`) — should carry into Session 2 naturally. Tested next turn. |

### Turn 14 — Talk with Lão Ngũ (NPC memory test)

**Player**: `Tiến đến quầy. "Lão tiên sinh sớm nay."`

**LLM**:
> Lão Ngũ ngẩng lên. Đôi mắt lão — hôm qua sắc và nghi ngờ — sáng nay vẫn vậy, nhưng có thêm một chút gì đó... không hẳn là ấm áp, nhưng đã qua vòng thử thách đầu.
>
> "Dậy sớm." Lão gấp tờ giấy, để xuống. "Mưa tạnh rồi. Đi đường đỡ khổ."
>
> Rồi lão thêm: "Vị du sĩ tối qua... rời đi lúc trời sắp sáng. Không ăn sáng, trả tiền trọ rồi đi thẳng ra cổng Bắc. Đi có vẻ vội."

| Annotation | Value |
|---|---|
| `fiction_duration` | ~45 sec |
| **NPC opinion persistence VALIDATED** | Lão Ngũ's response acknowledges prior encounter ("qua vòng thử thách đầu") — uses his Session-1 opinion state, not starting fresh. This is where session-scoped NPC-PC relationship memory (R8 `npc_pc_relationship`) is tested. |
| LLM improvised detail | Du sĩ "đi ra cổng Bắc, vội" = new L3 detail not canonical pre-this-turn; now it IS canonical (Lão Ngũ said so; NPC utterance = observable event). Future turns should respect this. → **Design implication**: NPC-emitted info via dialogue is first-class L3 canon. |
| Data-model need | On session resume, NPC-PC relationship state is loaded from `npc_pc_relationship` table; LLM prompt includes this in `[ACTOR_CONTEXT]` section (S9 prompt assembly) so LLM can tone responses accordingly |

### Turn 15 — Pursue Dương Quá plot hook

**Player**: `"Chuyện tiên bối nói tối qua... về tay kiếm trẻ ở Tương Dương. Tại hạ có nên đi xem thử không?"`

**LLM**:
> Lão Ngũ nhìn anh một lúc, như đang cân nhắc.
>
> "Cậu không có công phu gì — đi Tương Dương bây giờ chỉ chuốc khổ. Đường xa, trên đường có trộm cướp nhỏ. Nhưng..." lão ngừng, chép miệng, "nếu đã muốn đi thì đi. Tương Dương lúc này đông, dễ sống. Kiếm việc làm không khó, nếu cậu đọc được chữ. Về cái tay kiếm trẻ — đó là lời đồn. Đừng tin hết. Nhưng đúng là Tương Dương có chuyện."
>
> Rồi lão nhìn xuống hộp tiền của anh, chớp mắt. "Mà... cậu có đủ tiền đi đường không?"

| Annotation | Value |
|---|---|
| `fiction_duration` | ~1 min |
| **Plot-hook continuity VALIDATED** | Lão Ngũ remembers what he said Session 1 Turn 7 ("tay kiếm trẻ ở Tương Dương") without needing the player to re-cite it. This is NPC memory of own prior utterances. |
| Design implication | NPC state includes memory of its own statements to each PC. Either stored explicitly (`npc_pc_relationship.things_i_told_them jsonb`) or derivable from event log replay filtered by `actor=lao_ngu AND target_pc=ly_minh`. For V1, event-log replay is cheaper. |
| PC resource concern | Lão Ngũ notes PC's money situation — real constraint (PC has 15 đồng). Travel would need more. |
| Player decision point | Player can (a) still go anyway, (b) work for a few days to save money, (c) pursue different hook. Narrative branching. |

### Turn 16 — Declare long-duration travel (MV12 big jump test)

**Player**: `"Tại hạ quyết đi. Cảm ơn tiên bối đã chỉ đường."` Then: `/travel to Tương Dương by foot`

**System resolves**: Gia Hưng → Tương Dương by foot, autumn 1256. LLM estimates distance ~600km through Jiangnan terrain, realistic fiction-duration: 20-25 days. Player confirmation prompt (not shown) accepts.

**LLM (narration of compressed travel)**:
> Anh gật đầu với Lão Ngũ. Trả tiền bữa sáng ngắn Tiểu Thúy vừa mang ra — bánh bao và cháo loãng. Xong, anh đi ra cổng.
>
> *Hai mươi ba ngày đường sau.*
>
> Tương Dương hiện ra phía trước — một thành lớn giữa Jianghan bình nguyên. Tường thành đá xám, cao hơn anh tưởng. Chợ ngoài cổng Nam đông đúc — người buôn, phu khuân vác, lính gác, ăn mày. Gió cuối thu đã lạnh hơn Gia Hưng; áo ngoài của anh đã bạc thêm sau chuyến đi, giày cũng mòn gần hết.
>
> Trên đường, anh đã: ngủ ba đêm ở quán trọ nhỏ (tổng 18 đồng), hai đêm trong đình làng (miễn phí nhưng không yên), bị một đám đầu trâu mặt ngựa dọa dẫm ở huyện Vô Tích (may không có xảy ra gì — anh chạy nhanh), gặp một đoàn thương nhân đi chung một đoạn đường từ Nam Kinh xuống (trả công 10 đồng làm người ghi chép tạm).
>
> Trong túi còn khoảng 7 đồng. Người gầy hơn. Mắt quen với đường. Body-memory Hàng Châu mơ hồ đã phai dần; soul Sài Gòn 2026 tỉnh táo hơn, nhưng vẫn không biết tại sao mình ở đây.
>
> Mặt trời cao trên đầu. Cổng thành Nam — anh bước vào dòng người.

| Annotation | Value |
|---|---|
| `event_type` | `turn.time_advancement` (large duration) |
| `fiction_ts_start` | 1256/09/16 giờ Mão trung (~6am, after breakfast) |
| `fiction_duration` | ~23 days = 23 × 24h (resolved by LLM + player confirmation) |
| `fiction_ts_end` | 1256/10/09 giờ Ngọ sơ (~11am, autumn late) |
| **Calibration events fired** | `day_passes` × 23 + `month_passes` × 0 (9/16 → 10/9 spans month boundary) = actually should fire `month_passes` once at 9/30 → 10/1 boundary. Let me recount: 9/16 through 10/9 = 23 days + crosses month boundary once. So 23× `day_passes` + 1× `month_passes`. |
| **Design decision surfaced** | Calibration events fire on fiction-date-boundary crossings, not pure cumulative hours. (23 days of fiction = 23 `day_passes`, not 23×24/24=23 from cumulative — same math here but concept matters.) Refines MV12-D5. |
| LLM compressed narration | "Hai mươi ba ngày đường sau" — single narrative beat covers 23 days of intermediate events. Intermediate events NOT emitted as canonical (they're flavor). PC's narrative-declared outcome (money spent, body rustic, safe arrival) IS canonical. |
| Design implication | Large time-skips have **flavor narration** (non-canonical) + **structural deltas** (PC money −8, PC body-memory fade slightly, PC location=Tương Dương-cổng-Nam). Structural deltas are canonical events. |
| Cost state delta | Money 15 → ~7 (breakfast 3 + travel 8 net) — must be a canonical PCS event |
| Location state delta | PC location: Gia Hưng Yên Vũ Lâu → Tương Dương cổng Nam outskirts — reality state update |
| Scene transition | New scene entirely; old NPCs (Lão Ngũ, Tiểu Thúy) stay in reality at Yên Vũ Lâu but PC no longer in their scene |

### Turn 17 — Session 2 end / safe pause at Tương Dương

**Player**: `Tìm một quán trọ rẻ nhất gần cổng. Nghỉ ngơi, định hướng.`

**LLM**:
> Anh theo mùi thức ăn vào một con hẻm nhỏ phía Tây cổng Nam. Một cái biển gỗ nghiêng: "Lâm Khách Điếm" (林客店). Nhỏ hơn Yên Vũ Lâu, dơ hơn, rẻ hơn — chỉ có ba đồng một đêm cho một chỗ ngủ chung trong sảnh lớn, năm đồng cho phòng nhỏ.
>
> Anh chọn sảnh lớn ba đồng. Trả tiền cho một lão chủ quán béo mập, người này thậm chí không hỏi tên. Lão gật, đưa cho anh một manh chiếu rơm mỏng.
>
> Sảnh có khoảng bảy-tám khách hỗn tạp đang ngủ hoặc ngồi ngâm rượu. Mùi rơm ẩm, mùi người không tắm, mùi canh đậu. Anh tìm một góc gần tường, trải chiếu, ngồi xuống.
>
> Từ cửa sổ nhỏ, có thể thấy bức tường thành đá xám của Tương Dương in bóng trong nắng chiều. *Ở đây là nơi bắt đầu chuyện gì đó — nhưng anh chưa biết chuyện đó là gì.*

| Annotation | Value |
|---|---|
| `fiction_duration` | ~1h (find inn + transact + settle) |
| Money state delta | 7 → 4 đồng (3 đồng for dorm bed) |
| Scene boundary | Safe pause (PC in commoner dorm, anonymous, low-threat); good logout point |
| Session 2 ending fiction_ts | 1256/10/09 giờ Vị sơ (~1pm) |
| `current_fiction_ts` cumulative since reality start | Book anchor 1256/09/15 15:00 → 1256/10/09 13:00 = ~24 days total fiction-time elapsed in reality |
| Reality state at end | Gia Hưng Yên Vũ Lâu (Lão Ngũ + Tiểu Thúy still there in their fiction-time, unchanged since PC left) · PC now at Tương Dương Lâm Khách Điếm · du sĩ location unknown (left Yên Vũ Lâu pre-dawn; current location unspecified canonical) |

---

## 8. Session 2 Accumulated State

```
fiction_ts_start (session 2):  1256/09/15 giờ Thân trung +3min (Session 1 resume point)
fiction_ts_end (session 2):    1256/10/09 giờ Vị sơ (~1pm)
fiction_duration_total:        ~24 days fiction-time elapsed in this session
calibration_events_fired:      day_passes × 24, month_passes × 1 (9/30 → 10/1)

PC state at end of session 2:
  - Location: Tương Dương cổng Nam → Lâm Khách Điếm dorm
  - Money: 4 đồng (down from 15 at end of Session 1)
  - Soul state: more lucid than Session 1; xuyên-không shock receding
  - Body memory: Hàng Châu ancestry now "vague" (faded during travel); PC is increasingly his soul-self
  - Gear: áo bạc further worn, giày mòn, one chiếu rơm
  - Plot position: arrived at Dương Quá rumor city; no direct contact yet

NPC state persistence across sessions:
  - Yên Vũ Lâu NPCs (Lão Ngũ, Tiểu Thúy): UNCHANGED in reality state; if player returns
    to Yên Vũ Lâu at future fiction_ts > 1256/10/09, LLM will show "passed time" via
    new narration; their opinion of PC persists
  - Du sĩ: canonical exit "before dawn through cổng Bắc, heading Tương Dương direction";
    may re-encounter in later turns
  - (New NPCs in Tương Dương not yet introduced explicitly)

Plot hooks active:
  - Dương Quá Tương Dương rumor — PC has arrived at the place, has not pursued contact
  - Du sĩ mysterious destination — possibly overlapping with Dương Quá thread
```

---

## 9. Observations — What Session 2 Surfaced (beyond Session 1's 12)

| # | Surface | Design implication |
|---|---|---|
| 13 | Session-resume UX needs choice: continue vs /sleep X vs /travel X | Client UI at login shows "your PC is in state X — options ABC"; not auto-resume. Needs design in `features/04_play_loop/PL_004_session_boundary.md` |
| 14 | `turn.time_advancement` distinct from `turn.player_action` | Event taxonomy: time-advancement events don't emit narrative as canonical (flavor only); only structural deltas (money, location, state) are canonical. Design for `contracts/events/turn.*` schema |
| 15 | Calibration events fire on **fiction-date-boundary crossings**, not pure cumulative | Refines MV12-D5: `day_passes` fires when fiction_ts crosses midnight in reality's calendar; `month_passes` on month boundary; `year_passes` on year. Pure cumulative still possible if narrative events alone span 24h (rare). |
| 16 | Long time-skip narration = flavor + structural delta split | Flavor (LLM dreams, travel encounters) = non-canonical, re-generatable each retell. Structural (money -8, location change) = canonical events emitted. Need clear contract: "LLM narration during /travel or /sleep is flavor unless explicitly marked `emit=true`". |
| 17 | NPC opinion state persists across sessions (not just in-session) | `npc_pc_relationship` table (R8) is the persistence layer; session resume loads it. Prompt assembly (S9) reads it into `[ACTOR_CONTEXT]` so LLM responds contextually. |
| 18 | NPC memory of own utterances to specific PC | Either (a) `npc_pc_relationship.said_to_them[]` jsonb array of recent statements, OR (b) event-log replay filtered by `actor_id=X AND target_pc=Y AND event_type=npc_speech`. V1 pick (b) — cheaper, no new schema; LLM reads recent relevant events from event log in prompt context |
| 19 | Weather/ambient state transitions during time-skip | Weather is either (a) L3 reality-state field that updates on calibration events (rain → sunny via morning-calibration), OR (b) LLM-improvised per turn. V1 pick (b) for simplicity; LLM derives from fiction_ts hour + reality's climate axioms. |
| 20 | Reality state has "away" scenes that pause when PC not there | When PC leaves Yên Vũ Lâu, Lão Ngũ's scene frame "pauses" from PC's perspective but real fiction_ts advances globally. If another PC was at Yên Vũ Lâu, they'd continue interacting with Lão Ngũ during this time. For V1 solo-RP: no issue (one PC). Design for V2 coop: "scene" is scoped to active-session in that place; cross-scene fiction-ts is always global per-reality. |
| 21 | LLM inference of paused-mode routines (e.g., "Lão Ngũ would open shutters at dawn") | V1 decision: LLM can narrate these as flavor during time-advancement resolution. NOT events, NOT canonical. If consistency matters ("did Lão Ngũ sweep the floor this morning?"), LLM answers from best-guess each retell. V1+30d adds scheduled NPC routines for canonical behavior. |
| 22 | Player "intent" vs "PC plausibility" — PC just had body-transfer yesterday, would PC decide to travel? | Design tension: player-agency vs PC-coherence. V1 resolution: player decides what PC does; LLM narrates with some PC-psychology flavor ("anh quyết" — anh decided, not "anh miễn cưỡng bị lôi đi"). Not a solved tension, but acknowledged. |

**Combined Session 1 + Session 2 observation total: 22.**

---

## 10. MV12 Validation Summary

After Session 1 + Session 2, MV12 decisions validated with concrete tests:

| MV12 Decision | Validated by | Status |
|---|---|---|
| **D1** Page-turn time, cumulative from events | T1-T10 small events + T11 14h jump + T16 23-day jump all advance `current_fiction_ts` additively; no wall-clock ratio applied | ✅ Validated |
| **D2** Event sources (player + NPC autonomous + scheduled canon) | T1-T15 player turns drove; T11 sleep duration was player-declared; no NPC autonomous events (V1 paused); no scheduled canon events (none configured for this reality) | ✅ V1 scope validated; autonomous/scheduled deferred |
| **D3** Fiction-duration hybrid | System defaults used (T1 = 3s look, T4 = 2min sit-observe); player declared (T11 `/sleep until dawn`, T16 `/travel to Tương Dương`); LLM resolved (T11 ≈ 14h, T16 ≈ 23 days) | ✅ Validated across all 3 sources |
| **D4** V1 paused when 0 players | Between Session 1 logout and Session 2 login (~1.5h wall-clock), fiction_ts did NOT advance. Session 2 resumed at exact Session 1 end point. | ✅ Validated |
| **D5** Calibration events (cumulative + LLM-jump) | Refined to **date-boundary crossings** (see obs 15). `day_passes` × 24 + `month_passes` × 1 fired during Session 2. LLM-jump form used at T11 + T16. | ✅ Validated + refined |
| **D6** V1/V1+30d/V2+ split | Session 2 tested V1-only behavior (pause-when-solo). V1+30d (scheduled canon events) + V2+ (per-tier autonomous) not tested — future work. | ✅ V1 validated |
| **D7** Event schema additive per R3 | Every annotated turn's event carries `fiction_ts_start` + `fiction_duration`; `reality.current_fiction_ts` cumulative; `reality.book_anchor_fiction_ts` fixed to 1256/09/15 15:00. Schema form works in practice. | ✅ Validated |

**No MV12 re-opens needed.** D5 gets refinement note (fire on date-boundary, not cumulative hours).

---

## 11. Graduation Path (updated from Session 1 list)

Post Session 1 + Session 2 review, observations feed into:

| Observation area | Target feature subfolder |
|---|---|
| NPC state structure (obs 1, 6, 9, 17, 18) | `features/05_npc_systems/NPC_001_npc_state_model.md` (new) — session-scoped memory + NPC own-utterance recall + per-PC opinion state |
| PC sheet persona-layering (obs 2, 12, 22) | `features/06_pc_systems/PCS_001_persona_and_body_memory.md` (new) — soul/body-memory split + player-intent-vs-PC-plausibility guidance |
| Fiction-duration defaults + event taxonomy (obs 3, 7, 14, 16) | `features/04_play_loop/PL_001_turn_duration_defaults.md` (new) — default table + `turn.time_advancement` vs `turn.player_action` event-type split + flavor-vs-structural narration rule |
| Scene model + ambient events + weather (obs 4, 10, 19, 20) | `features/04_play_loop/PL_002_scene_model.md` (new) — scene_id + ambient_events jsonb + weather-derivation rule + per-scene vs per-reality fiction_ts scope (V2 coop concern) |
| L1 enforcement in prompt assembly (obs 5, 11) | Kernel extension on-demand: extend `02_storage/S09_prompt_assembly.md` with L1-axiom injection rule in `[WORLD_CANON]` section |
| Multi-NPC batched response (obs 6) | `features/04_play_loop/PL_003_multi_npc_turn.md` (new) — single-LLM-call multi-NPC reaction pattern |
| Safe-pause detection + session-resume UX (obs 8, 13) | `features/04_play_loop/PL_004_session_boundary.md` (new) — `safe_pause=true` emission + login-time option UX (continue / sleep X / travel X / wake now) |
| Paused-mode routine flavor narration (obs 21) | `features/12_daily_life/DL_001_npc_routine_foundations.md` (V1+30d new) — canonical vs flavor distinction for NPC routines |
| Session 2 resume mechanics (obs 13) | `features/DF/DF05_session_group_chat/` (when designed) — part of session lifecycle |

**MV12 status post-spike:**

- **D1..D4, D6, D7 validated as-is** — Session 2 concrete tests matched decisions.
- **D5 refined** (not re-opened, just clarified): calibration events fire on fiction-**date-boundary** crossings, not pure cumulative hours. Add note to MV12-D5 row in `decisions/locked_decisions.md` during next kernel cascade.

**Candidate new MV12 decisions surfaced** (not yet locked; defer to feature-design that consumes them):

- **MV12-D8** Time-skip narration taxonomy — flavor (LLM-regenerable, non-canonical) vs structural delta (money / location / PC state — canonical event emit). Natural home: locked when `PL_001_turn_duration_defaults.md` formalizes event taxonomy.
- **MV12-D9** Scene-scope vs reality-scope fiction_ts — per-reality global fiction_ts is canonical (V1 solo-RP trivial). Per-scene concept needed V2 coop (multiple PCs in different scenes within same reality). Natural home: locked when `PL_002_scene_model.md` designs scene concept.
- **MV12-D10** Paused-mode narrative fill — LLM can narrate "what would naturally happen during time-skip" as flavor during V1 paused mode; not canonical. V1+30d may upgrade to scheduled NPC routines for canonical behavior. Natural home: locked when `DL_001_npc_routine_foundations.md` designs NPC routines.
- **MV12-D11** Book-anchor drift policy — after N days of fiction-time past anchor, does the reality become "not-really-that-book" anymore? No test surfaced this need in Session 1+2 (still only 24 days in); deferred until play-time data shows real drift. Likely V2+ concern.
