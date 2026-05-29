# lore-enrichment — demo source data

Public-domain source corpus for the lore-enrichment demo (封神演义 place enrichment).

## `fengshen-yanyi.txt`
- **Work:** 封神演義 (Fengshen Yanyi / Investiture of the Gods), Ming dynasty (~16th c.), attrib. 许仲琳. **Public domain.**
- **Source:** Chinese Wikisource — `https://zh.wikisource.org/wiki/封神演義` (pages `封神演義/卷001`…`卷100`).
- **Fetched:** 2026-05-30 via the MediaWiki extracts API (`action=query&prop=extracts&explaintext=1`), 100/100 chapters, concatenated with `========== 第N回 ==========` markers. UTF-8 (no BOM), ~601k chars.
- **Demo relevance (verified):** target under-described places all present in canon — 朝歌, 西岐, 蓬萊, 玉虛宮, 碧遊宮, 八景宮, 火雲洞, 陳塘關. These are the gap-detection targets for the place-focused demo (history/geography/culture enrichment).

### Re-fetch (if needed)
PowerShell loop over `封神演義/卷{001..100}` against the Wikisource extracts API with retry+backoff (see session history / commit message). No login or key required.

## Still to fetch (technique-b cultural corpora — at/near cycle C10)
- **山海经 (Shan Hai Jing)** — public domain; ctext.org/shan-hai-jing + Wikisource. Not yet downloaded.
- **Shang–Zhou (商周) history** references — public-domain classics.

> Sources are public-domain; safe to commit. Modern/news sources (technique d, P3) require separate licensing review.
