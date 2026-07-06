"""Japanese (ja) intent keywords. Unspaced script ⇒ matched bare. Alternation bodies."""

from __future__ import annotations

# Past — 昔 (long ago) / 何年も前 (years ago) / 最初は·元々 (originally) /
# かつて (once).
HISTORICAL_STRONG = r"昔|何年も前|数年前|最初は|元々|もともと|かつて|当初"

# Weaker past — 以前 (before/previously) / 前に (earlier).
HISTORICAL_WEAK = r"以前|前に|先に"

# Present/near — たった今·今しがた (just now) / 今·現在 (now) / この章 (this chapter).
RECENT = r"たった今|今しがた|さっき|今|現在|この章|ちょうど今"

# Relational — 知って·知り合い·会った·出会 (know/meet) / 関係·との間·繋がり /
# 友達·敵 (friend/enemy) / 結婚·同盟 (married/allied) / ライバル (rival).
RELATIONAL_KEYWORDS = (
    r"知って|知り合い|会った|会って|出会|関係|との間|繋がり|つながり|"
    r"一緒|友達|友人|敵|結婚|同盟|ライバル|仲間"
)

# Explicit relational phrasings.
RELATIONAL_STRONG = r"の関係|誰が知って|誰と|の繋がり|どういう関係|どんな関係"
