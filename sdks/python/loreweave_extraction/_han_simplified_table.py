"""Vendored, FROZEN traditional→simplified Han character table (Phase 1).

D-KG-TL-SIMPLIFIED-TRADITIONAL-DUP. Used by ``name_normalize.fold_han_simplified``
to fold CJK simplified/traditional variants of the SAME entity name to one
canonical (simplified) form, so 張若塵 and 张若尘 dedup to one ``:Entity``.

WHY a vendored table and not opencc/hanziconv: ``entity_canonical_id`` must be
deterministic FOREVER (it is the Neo4j node key — re-extracting the same source
must yield the same id). An external lib could change its mapping between versions
and silently re-key every CJK entity. A frozen, in-repo table guarantees stability.

⚠️ Phase-1 STARTER SET — a curated subset of high-frequency, high-confidence
traditional→simplified pairs (the common characters + the live-smoke cast). It is
INTENTIONALLY incomplete: a rare character simply doesn't fold (a residual
duplicate, no worse than today — additive). The migration phase replaces this with
a complete OpenCC-derived `t2s` mapping; the public API (`fold_han_simplified`)
does not change when the table grows.

Each entry is traditional → simplified. Characters that are identical in both
scripts are NOT listed (the fold is a no-op for them). Verified pairs only — a
WRONG entry would corrupt canonicalization, so correctness beats coverage here.
"""

from __future__ import annotations

# traditional : simplified — high-frequency, individually verified.
T2S: dict[str, str] = {
    # live-smoke cast (万古神帝) + their components
    "張": "张", "塵": "尘", "瑤": "瑶", "龍": "龙", "萬": "万",
    "鳳": "凤", "雲": "云", "靈": "灵", "聖": "圣", "帝": "帝",
    # ultra-common characters
    "與": "与", "國": "国", "學": "学", "來": "来", "時": "时",
    "這": "这", "們": "们", "個": "个", "馬": "马", "鳥": "鸟",
    "魚": "鱼", "門": "门", "開": "开", "關": "关", "長": "长",
    "車": "车", "見": "见", "貝": "贝", "風": "风", "飛": "飞",
    "東": "东", "書": "书", "畫": "画", "愛": "爱", "樂": "乐",
    "義": "义", "會": "会", "體": "体", "點": "点", "黨": "党",
    "兒": "儿", "頭": "头", "麗": "丽", "寶": "宝", "劍": "剑",
    "過": "过", "還": "还", "進": "进", "種": "种", "樣": "样",
    "員": "员", "動": "动", "務": "务", "號": "号", "將": "将",
    "軍": "军", "師": "师", "陽": "阳", "陰": "阴", "戰": "战",
    "殺": "杀", "術": "术", "華": "华", "黃": "黄", "葉": "叶",
    "趙": "赵", "錢": "钱", "孫": "孙", "韓": "韩", "楊": "杨",
    "鄭": "郑", "陳": "陈", "衛": "卫", "嚴": "严", "許": "许",
    "蘇": "苏", "顧": "顾", "鄧": "邓", "獨": "独", "獸": "兽",
    "現": "现", "產": "产", "發": "发", "盡": "尽", "競": "竞",
    "筆": "笔", "紅": "红", "純": "纯", "細": "细", "終": "终",
    "經": "经", "結": "结", "給": "给", "絕": "绝", "統": "统",
    "綠": "绿", "維": "维", "網": "网", "緊": "紧", "縣": "县",
    "總": "总", "繼": "继", "續": "续", "羅": "罗", "聯": "联",
    "聲": "声", "職": "职", "興": "兴", "舉": "举", "舊": "旧",
    "藥": "药", "蘭": "兰", "處": "处", "裝": "装", "裡": "里",
    "製": "制", "複": "复", "規": "规", "視": "视", "覽": "览",
    "觀": "观", "計": "计", "記": "记", "設": "设", "話": "话",
    "認": "认", "語": "语", "說": "说", "課": "课", "調": "调",
    "請": "请", "謝": "谢", "證": "证", "識": "识", "議": "议",
    "護": "护", "讀": "读", "變": "变", "讓": "让", "豐": "丰",
    "財": "财", "責": "责", "貴": "贵", "買": "买", "費": "费",
    "資": "资", "賢": "贤", "賣": "卖", "賴": "赖", "趨": "趋",
    "輪": "轮", "輸": "输", "轉": "转", "農": "农", "運": "运",
    "達": "达", "遠": "远", "適": "适", "遲": "迟", "選": "选",
    "遺": "遗", "鄉": "乡", "釋": "释", "鋼": "钢", "錄": "录",
    "錯": "错", "鍵": "键", "鎮": "镇", "鏡": "镜", "鐵": "铁",
    "鑰": "钥", "閃": "闪", "間": "间", "陸": "陆", "隊": "队",
    "階": "阶", "際": "际", "隨": "随", "險": "险", "隱": "隐",
    "雖": "虽", "雙": "双", "離": "离", "難": "难", "電": "电",
    "霧": "雾", "靜": "静", "韓": "韩", "響": "响", "頁": "页",
    "順": "顺", "預": "预", "領": "领", "題": "题", "願": "愿",
    "類": "类", "顯": "显", "飄": "飘", "養": "养", "餘": "余",
    "館": "馆", "馳": "驰", "驅": "驱", "驚": "惊", "骨": "骨",
    "高": "高", "鬥": "斗", "鬧": "闹", "魂": "魂", "魔": "魔",
    "魯": "鲁", "鮮": "鲜", "鯨": "鲸", "鳴": "鸣", "鵬": "鹏",
    "鶴": "鹤", "鷹": "鹰", "鹽": "盐", "麥": "麦", "麵": "面",
    "麼": "么", "齊": "齐", "齒": "齿", "龐": "庞", "龜": "龟",
}

__all__ = ["T2S"]
