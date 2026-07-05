"""Korean (ko) intent keywords. Unspaced (agglutinative) ⇒ matched bare — stems
without a trailing josa so 알다/알고/알아 all hit. Alternation bodies."""

from __future__ import annotations

# Past — 오래전 (long ago) / 몇 년 전 (years ago) / 원래·처음에 (originally) /
# 한때 (once).
HISTORICAL_STRONG = r"오래전|오래 전|몇 년 전|여러 해 전|원래|처음에|한때|당초"

# Weaker past — 전에 (before) / 이전에 (previously).
HISTORICAL_WEAK = r"전에|이전|예전"

# Present/near — 방금 (just now) / 지금·현재 (now/currently) / 이 장 (this chapter).
RECENT = r"방금|막|지금|현재|이 장|이번 장|바로 지금"

# Relational — 알(다) (know) / 만나·만났 (meet) / 관계·사이 (relationship/between) /
# 친구·적 (friend/enemy) / 결혼·동맹 (married/allied) / 라이벌 (rival).
RELATIONAL_KEYWORDS = (
    r"알고|아는|알아|만나|만났|관계|사이|함께|친구|적|"
    r"결혼|동맹|라이벌|연결|아군"
)

# Explicit relational phrasings.
RELATIONAL_STRONG = r"의 관계|누가 아는|누구를|어떤 관계|무슨 관계|사이가"
