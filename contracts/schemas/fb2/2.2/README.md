# FictionBook 2.2 XML Schemas

These files are vendored from the FictionBook 2.2 schema distribution.

- Canonical source: `http://www.gribuser.ru/xml/fictionbook/2.2/xsd/`
- Mirror requested for discovery: `https://www.beroal.in.ua/human/fiction_book/`
- Retrieved: 2026-08-02. Upstream ships legacy CR/CRLF separators; **all four files are normalized to LF here**, as `.gitattributes` (`* text=auto eol=lf`) does for every text file, so each checkout gets identical bytes on every platform.
- **The hashes below are of the normalized files as committed**, which is what `sha256sum -c SHA256SUMS` verifies. They are therefore not the hashes of the raw upstream downloads. Three of them originally recorded the pre-normalization bytes and could never verify; a manifest that cannot pass is worse than none, so they were recomputed against the committed content.
- Compatibility: FB2 2.2 retains the `http://www.gribuser.ru/xml/fictionbook/2.0` XML namespace. The importer accepts that namespace and implements a bounded, safe import subset; it does not execute or resolve XML DTDs or external entities.

| File | SHA-256 |
| --- | --- |
| `FictionBook2.2.xsd` | `37e8a634d8eddbdb9a4eb8694a7d1dbfa79b2fe61499672af5d53304f3a30365` |
| `FictionBookGenres.xsd` | `f5e3538a399a626d3fa781cf33024e3d56415f1affb4271edb44823cf561d506` |
| `FictionBookLang.xsd` | `569aee0bc1f30d60f4415a0d832a99ac78e38d02ceac18e83affc353ea0e77b7` |
| `FictionBookLinks.xsd` | `f4697d9a42f191a9030b74f7611dd340b0298860b5eb30e67ea6560b52ff6af6` |

The upstream XSD files retain their original copyright and redistribution notice.
