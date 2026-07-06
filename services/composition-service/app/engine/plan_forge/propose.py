"""Propose NovelSystemSpec from PlanDocument (rules-first; fixture-quality for POC)."""

from __future__ import annotations

import re
from typing import Any

from app.engine.plan_forge.normalize import post_normalize_spec


def _section(doc: dict[str, Any], kind: str) -> dict[str, Any] | None:
    for s in doc.get("sections", []):
        if s["kind"] == kind:
            return s
    return None


def _sections(doc: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [s for s in doc.get("sections", []) if s["kind"] == kind]


def _extract_open_questions(body: str) -> list[str]:
    items: list[str] = []
    for line in body.splitlines():
        m = re.match(r"^-\s+\[\s*\]\s+(.+)$", line.strip())
        if m:
            items.append(m.group(1).strip())
    return items


def _extract_consistency_anchors(char_body: str) -> list[str]:
    anchors = [
        "Bình dị trong tâm hồn — hạnh phúc trong thứ nhỏ (bát mì, quán trà, tiếng trẻ)",
        "Hài hước khô (dry humor) trong độc thoại — giảm dần theo Đạo Hóa",
        "Ngoại hình baseline bình thường — contrast với hoàn mỹ quái dị sau Đạo Hóa",
        "Giữ lý trí trong khủng hoảng — trait không biến mất hoàn toàn",
        "Thực dụng trước tiên — tính toán trước khi hành động",
        "Mối quan hệ với cái đẹp: thích mà không cần sở hữu",
    ]
    found: list[str] = []
    body_lower = char_body.lower()
    if "bình dị" in body_lower or "bát mì" in body_lower:
        found.append(anchors[0])
    if "hài hước" in body_lower or "dry humor" in body_lower:
        found.append(anchors[1])
    if "bình thường" in body_lower or "ngoại hình" in body_lower:
        found.append(anchors[2])
    if "lý trí" in body_lower or "khủng hoảng" in body_lower:
        found.append(anchors[3])
    if "thực dụng" in body_lower:
        found.append(anchors[4])
    if "cái đẹp" in body_lower:
        found.append(anchors[5])
    return found or anchors[:4]


def _variable_defs(var_body: str) -> list[dict[str, Any]]:
    return [
        {
            "code": "PA",
            "name": "Perfection_Addiction",
            "range": "0 → 100+",
            "transition_rules": [
                "Tăng mỗi lần đạt hoàn mỹ / perfection experience",
                "Ngưỡng unlock tier: 20 / 50 / 80",
                "Không tăng/giảm theo cảnh giới — chỉ theo trải nghiệm",
            ],
            "not_coupled_to": ["cultivation_realm", "cảnh giới"],
        },
        {
            "code": "HA",
            "name": "Humanity_Anchor",
            "range": "100 → 0",
            "transition_rules": [
                "Giảm dần theo PA tăng và thời gian",
                "Neo điểm: khoảnh khắc bình dị của cuộc sống",
                "Không tăng/giảm theo cảnh giới — chỉ theo trải nghiệm",
            ],
            "not_coupled_to": ["cultivation_realm", "cảnh giới"],
        },
        {
            "code": "CD",
            "name": "Corruption_Debt",
            "range": "tích lũy ngầm",
            "transition_rules": [
                "Tăng mỗi lần luyện công pháp fake",
                "Bộc phát không theo lịch — planner chọn thời điểm bất ngờ",
                "Không visible cho nhân vật",
            ],
            "not_coupled_to": ["cultivation_realm"],
        },
        {
            "code": "THR",
            "name": "Than_Hon_Resonance",
            "range": "seed tiền kiếp",
            "transition_rules": [
                "Rò rỉ qua mộng, ảo giác, déjà vu",
                "Tăng khi gặp trigger Mị Đế",
                "Long-game — không giải thích trực tiếp ở arc sớm",
            ],
            "not_coupled_to": [],
        },
    ]


def _parse_events_in_block(arc_id: str, body: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    parts = re.split(r"\n### ", body)
    for part in parts:
        if not part.strip():
            continue
        if not part.strip().lower().startswith("event"):
            continue
        lines = part.strip().splitlines()
        header = "### " + lines[0]
        # The LAST event in a block has no following "### " to split on, so
        # without this it swallows the arc's trailing "---"-delimited closing
        # summary (e.g. "**Trạng thái cuối Arc N:**...") as part of its own
        # body — spuriously matching var_delta regexes meant for other events.
        ev_body = "\n".join(lines[1:]).split("\n---", 1)[0]
        m = re.match(r"### Event (\d+)", header)
        num = m.group(1) if m else str(len(events) + 1)
        ev_id = f"{arc_id}_event_{num}"
        events.append(_parse_event_block(ev_id, arc_id, header, ev_body))
    return events


def _parse_arcs_and_events(arc_body: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    arcs: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    arc_blocks = re.split(r"\n## ", arc_body)
    for block in arc_blocks:
        if not block.strip():
            continue
        lines = block.strip().splitlines()
        header = lines[0].strip()
        body = "\n".join(lines[1:])

        if re.match(r"Arc 1", header, re.I):
            arcs.append(
                {
                    "id": "arc_1",
                    "title": "Arc 1",
                    "theme": "Mất linh căn — kiệt sức nhưng chưa đầu hàng",
                    "arc_kind": "setup",
                    "summary": "Nữ chính bị đào linh căn, mất địa vị và tương lai tu tiên chính thống",
                }
            )
        elif re.match(r"\[TRANSITION\]", header, re.I):
            events.append(_parse_event_block("transition_event_8", "transition", "### " + header, body))
        elif re.match(r"Arc 2", header, re.I):
            arcs.append(
                {
                    "id": "arc_2",
                    "title": "Bước Lên Tiên Lộ",
                    "theme": "Arc khám phá và trả giá — không phải arc sức mạnh",
                    "arc_kind": "discovery",
                    "summary": "Phàm nhân mất linh căn bước lên con đường tu luyện không ai biết",
                    "exit_state": {"PA": 15, "HA": 85, "CD": 5, "THR": 2, "tier": "tier_1"},
                }
            )
            events.extend(_parse_events_in_block("arc_2", body))

    return arcs, events


def _parse_event_block(
    ev_id: str, arc_id: str, header: str, body: str
) -> dict[str, Any]:
    title = header.replace("### ", "").strip()
    goal_m = re.search(r"\*\*Goal:\*\*\s*(.+)", body)
    goal = goal_m.group(1).strip() if goal_m else ""

    notes: list[str] = []
    for m in re.finditer(r"\*\*Planner note[^:]*:\*\*\s*(.+)", body, re.I):
        notes.append(m.group(1).strip())

    var_deltas: list[dict[str, Any]] = []
    if re.search(r"HA\s*=\s*100", body, re.I):
        var_deltas.append(
            {"variable": "HA", "delta": "hold=100", "reason": "baseline preserved", "coupled_to_realm": False}
        )
    if re.search(r"PA\s*\+1|PA khởi động", body, re.I):
        var_deltas.append(
            {"variable": "PA", "delta": "+1", "reason": "first perfection sensation", "coupled_to_realm": False}
        )
    if re.search(r"PA \+lớn|PA tăng mạnh", body, re.I):
        var_deltas.append(
            {"variable": "PA", "delta": "+large", "reason": "first breakthrough perfection", "coupled_to_realm": False}
        )
    if re.search(r"CD tăng", body, re.I):
        var_deltas.append(
            {"variable": "CD", "delta": "+1", "reason": "first backlash", "coupled_to_realm": False}
        )
    if re.search(r"THR", body, re.I):
        var_deltas.append(
            {"variable": "THR", "delta": "+leak", "reason": "past-life pattern", "coupled_to_realm": False}
        )

    synopsis_lines = []
    for line in body.splitlines():
        if line.startswith("**") or line.startswith(">"):
            continue
        if line.strip() and not line.startswith("-"):
            synopsis_lines.append(line.strip())
            if len(synopsis_lines) >= 3:
                break
    synopsis = " ".join(synopsis_lines)[:500] if synopsis_lines else title

    return {
        "id": ev_id,
        "arc_id": arc_id,
        "title": title,
        "synopsis": synopsis,
        "goal": goal,
        "planner_notes": notes,
        "var_deltas": var_deltas,
    }


def propose_spec(doc: dict[str, Any]) -> dict[str, Any]:
    char_sec = _section(doc, "character_seed")
    var_sec = _section(doc, "planner_variables")
    arc_sec = _section(doc, "arc_overview")
    principles_sec = _section(doc, "writing_principles")
    open_sec = _section(doc, "open_questions")
    mech_secs = _sections(doc, "mechanics")

    char_body = char_sec["body"] if char_sec else ""
    anchors = _extract_consistency_anchors(char_body)

    mechanics: list[dict[str, Any]] = []
    for i, ms in enumerate(mech_secs):
        mechanics.append(
            {
                "id": f"mechanic_{i + 1}",
                "name": ms["title"],
                "rules": [line.strip("- ").strip() for line in ms["body"].splitlines() if line.strip().startswith("-")][:8],
                "planner_secrets": [
                    ln.strip()
                    for ln in ms["body"].splitlines()
                    if "Planner Secret" in ln or "KHÔNG TIẾT LỘ" in ln
                ],
            }
        )

    arcs, events = _parse_arcs_and_events(arc_sec["body"] if arc_sec else "")

    forbids = [
        "Không tiết lộ Planner Secret 1 (công pháp fake) cho nhân vật",
        "Không giải thích THR/tiền kiếp trực tiếp ở arc sớm",
        "Không miêu tả Đạo Hóa bằng hành vi trực tiếp — chỉ qua nội tâm và ẩn dụ",
        "Tránh điên loạn ngay từ đầu — giữ lý trí và đấu tranh nội tâm",
    ]
    style = []
    if principles_sec:
        for line in principles_sec["body"].splitlines():
            if line.strip().startswith("-"):
                style.append(line.strip("- ").strip())

    links: list[dict[str, Any]] = []
    for ev in events:
        for nd in ev.get("var_deltas", []):
            links.append(
                {
                    "from": ev["id"],
                    "to": nd["variable"],
                    "kind": "event_constrains_variable",
                    "note": nd.get("reason", ""),
                }
            )
        for note in ev.get("planner_notes", []):
            if "baseline" in note.lower() or "hài hước" in note.lower():
                links.append(
                    {
                        "from": ev["id"],
                        "to": "charter.consistency_anchors",
                        "kind": "event_preserves_anchor",
                        "note": note,
                    }
                )
            if "THR" in note:
                links.append(
                    {
                        "from": ev["id"],
                        "to": "THR",
                        "kind": "event_foreshadows",
                        "note": note,
                    }
                )

    open_q = _extract_open_questions(open_sec["body"]) if open_sec else []

    return post_normalize_spec(
        {
            "version": 1,
            "meta": {
                "title": "STORY PLAN",
                "version_label": "v1.0",
                "source_checksum": doc["source"]["checksum_sha256"],
                "open_questions": open_q,
            },
            "charter": {
                "consistency_anchors": anchors,
                "forbids": forbids,
                "style_constraints": style[:10],
            },
            "layers": {
                "characters": [
                    {
                        "id": "protagonist",
                        "name": "[TBD]",
                        "role": "protagonist",
                        "traits": [
                            "thực dụng",
                            "bình dị",
                            "dry humor",
                            "giữ lý trí",
                            "tự giác giới hạn",
                        ],
                        "baseline_notes": "Người hiện đại xuyên không; phế nhân sau đào linh căn",
                    }
                ],
                "mechanics": mechanics,
                "variables": _variable_defs(var_sec["body"] if var_sec else ""),
            },
            "arcs": arcs,
            "events": events,
            "links": links,
        }
    )
