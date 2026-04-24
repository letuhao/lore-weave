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

## 7. Next Step: Session 2

To be drafted after Session 1 review. Session 2 will test:

1. **MV12-D4 V1 pause semantics** — PC logs back in; fiction_ts still at Turn 10 end; LLM resumes with "Anh mở mắt" narration
2. **Player-declared time advancement** — Player declares `/sleep 8 hours`; LLM advances fiction_ts by 8h (calibration event MV12-D5 "morning arrives" fires); new scene state (different light, perhaps different ambient)
3. **NPC state persistence across session boundary** — Lão Ngũ's opinion + Tiểu Thúy's curiosity should still be there. Du sĩ may have left.
4. **Plot-hook continuity** — Dương Quá rumor still exists; PC can pursue or ignore
5. **New events trigger** — post-dawn scene (different NPCs present; different weather; maybe Lão Ngũ not at quầy)
6. **Observations on cross-session state recovery** — what does the SDK need to do on session resume?

---

## 8. Graduation Path

Post Session 1 + Session 2 review, observations feed into:

| Observation area | Target feature subfolder |
|---|---|
| NPC state structure (obs 1, 6, 9) | `features/05_npc_systems/NPC_001_npc_state_model.md` (new) |
| PC sheet persona-layering (obs 2, 12) | `features/06_pc_systems/PCS_001_persona_and_body_memory.md` (new) |
| Fiction-duration defaults table (obs 3, 7) | `features/04_play_loop/PL_001_turn_duration_defaults.md` (new) |
| Scene model + ambient events (obs 4, 10) | `features/04_play_loop/PL_002_scene_model.md` (new) |
| L1 enforcement in prompt assembly (obs 5, 11) | Kernel extension on-demand: extend `02_storage/S09_prompt_assembly.md` with L1-axiom injection rule |
| Multi-NPC batched response (obs 6) | `features/04_play_loop/PL_003_multi_npc_turn.md` (new) |
| Safe-pause detection (obs 8) | `features/04_play_loop/PL_004_session_boundary.md` (new) |
| Session 2 resume mechanics | `features/DF/DF05_session_group_chat/` (when designed) |

MV12 D1-D7 remain locked. Session 2 may surface D8 (miss-out severity) or D9 (book-anchor drift policy) as new decisions.
