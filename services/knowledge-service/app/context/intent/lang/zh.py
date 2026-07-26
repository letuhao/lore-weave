"""Chinese (zh) intent keywords — common, unambiguous terms. Unspaced script ⇒
matched bare (no `\\b`) by the registry. Alternation bodies."""

from __future__ import annotations

# Past anchors — 很久以前 (long ago) / 多年前 (years ago) / 几章前 (chapters ago) /
# 最初·原本 (originally) / 曾经 (once).
HISTORICAL_STRONG = r"很久以前|多年前|几章前|幾章前|最初|原本|曾经|曾經|当初|當初"

# Weaker past — 之前 (before) / 早先·先前 (earlier/previously).
HISTORICAL_WEAK = r"之前|早先|先前|以前"

# Present/near — 刚刚·刚才 (just now) / 现在·此刻·目前 (right now/currently) /
# 这一章·这章 (this chapter).
RECENT = r"刚刚|刚才|剛剛|剛才|现在|現在|此刻|目前|这一章|這一章|这章|這章|正在"

# Relational — 认识·知道·见过·遇见 (know/met) / 关系·之间·联系 (relationship/between) /
# 朋友·敌人 (friend/enemy) / 结婚·结盟·对手 (married/allied/rival).
RELATIONAL_KEYWORDS = (
    r"认识|認識|知道|见过|見過|遇见|遇見|关系|關係|之间|之間|"
    r"联系|聯繫|一起|朋友|敌人|敵人|结婚|結婚|结盟|結盟|对手|對手|盟友"
)

# Explicit relational phrasings.
RELATIONAL_STRONG = (
    r"之间的关系|之間的關係|之间的联系|之間的聯繫|谁认识|誰認識|谁知道|誰知道|"
    r"是什么关系|是什麼關係|有什么关系|有什麼關係"
)
