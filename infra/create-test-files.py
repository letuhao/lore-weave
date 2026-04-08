"""Create rich test files for import quality testing."""
import zipfile
import os
import sys

outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ.get('TEMP', '/tmp'), 'import-quality')
os.makedirs(outdir, exist_ok=True)

# === 1. Complex .docx ===
content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>'''

rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''

document = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Chapter One: The Beginning</w:t></w:r></w:p>
    <w:p><w:r><w:t xml:space="preserve">The sun rose slowly over the mountains, casting long shadows across the valley below. It was a </w:t></w:r><w:r><w:rPr><w:b/></w:rPr><w:t>beautiful morning</w:t></w:r><w:r><w:t>, the kind that made you want to stay in bed.</w:t></w:r></w:p>
    <w:p><w:r><w:rPr><w:i/></w:rPr><w:t>"I should get moving,"</w:t></w:r><w:r><w:t xml:space="preserve"> she thought, pulling the covers tighter.</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>The First Sign</w:t></w:r></w:p>
    <w:p><w:r><w:t>The letter arrived at noon. It bore the seal of the Royal Academy.</w:t></w:r></w:p>
    <w:p><w:r><w:rPr><w:b/><w:i/></w:rPr><w:t>Important Notice:</w:t></w:r><w:r><w:t xml:space="preserve"> All students must report by the first day of autumn.</w:t></w:r></w:p>
  </w:body>
</w:document>'''

word_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'''

docx_path = os.path.join(outdir, 'quality-test.docx')
with zipfile.ZipFile(docx_path, 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('[Content_Types].xml', content_types)
    z.writestr('_rels/.rels', rels)
    z.writestr('word/document.xml', document)
    z.writestr('word/_rels/document.xml.rels', word_rels)
print(f'docx: {docx_path}')

# === 2. Multi-chapter .epub ===
container_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>'''

content_opf = '''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">test-epub-001</dc:identifier>
    <dc:title>The Silver Phoenix</dc:title>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch3" href="chapter3.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="ch1"/>
    <itemref idref="ch2"/>
    <itemref idref="ch3"/>
  </spine>
</package>'''

ch1 = '''<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Chapter 1</title></head>
<body>
<h1>Chapter 1: The Awakening</h1>
<p>In the ancient city of <em>Luminara</em>, where towers of crystal caught the morning light, a young woman named <strong>Aria</strong> opened her eyes for the first time in a thousand years.</p>
<p>The chamber around her was cold and dark. Dust covered every surface, and the magical seals on the walls had long since faded to nothing.</p>
<blockquote><p>"Time is but a river," the old texts said, "and we are merely leaves upon its current."</p></blockquote>
<p>She rose slowly, her joints stiff from centuries of sleep. The world she remembered was gone.</p>
</body>
</html>'''

ch2 = '''<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Chapter 2</title></head>
<body>
<h1>Chapter 2: The New World</h1>
<p>The streets of Luminara were unrecognizable. Where once grand bazaars had bustled with merchants from across the realm, now only silence remained.</p>
<h2>The Ruins</h2>
<p>Aria walked through the <strong>broken archways</strong> and <em>crumbling facades</em>, each step echoing in the emptiness. She noticed several changes:</p>
<ul>
<li>The Great Library had collapsed entirely</li>
<li>The River of Stars had dried to a trickle</li>
<li>Strange metal structures dotted the landscape</li>
</ul>
<h2>A Stranger</h2>
<p>"Who are you?" The voice came from behind a fallen column. A boy, no older than fifteen, peered at her with wide eyes.</p>
<p>"My name is Aria," she said. "I am... I <em>was</em> the Guardian of the Crystal Spire."</p>
</body>
</html>'''

ch3 = '''<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Chapter 3</title></head>
<body>
<h1>Chapter 3: The Quest Begins</h1>
<p>The boy\u2019s name was <strong>Kael</strong>. He led Aria through the ruins to a small camp hidden beneath the old aqueduct.</p>
<p>"There are others," he explained. "We\u2019ve been waiting for someone like you. Someone from the <em>Before Times</em>."</p>
<p>Aria looked at the ragged group gathered around the fire. Their faces told stories of hardship, but their eyes held something she recognized: <strong>hope</strong>.</p>
<p>"What happened here?" she asked, dreading the answer.</p>
<p>Kael\u2019s expression darkened. "The Sundering. A great war between the mages. They tore the world apart."</p>
<hr/>
<p><em>To be continued...</em></p>
</body>
</html>'''

epub_path = os.path.join(outdir, 'quality-test.epub')
with zipfile.ZipFile(epub_path, 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('mimetype', 'application/epub+zip')
    z.writestr('META-INF/container.xml', container_xml)
    z.writestr('OEBPS/content.opf', content_opf)
    z.writestr('OEBPS/chapter1.xhtml', ch1)
    z.writestr('OEBPS/chapter2.xhtml', ch2)
    z.writestr('OEBPS/chapter3.xhtml', ch3)
print(f'epub: {epub_path}')

# === 3. Rich .txt ===
txt_path = os.path.join(outdir, 'quality-test.txt')
with open(txt_path, 'w', encoding='utf-8') as f:
    f.write("""The Last Guardian

In the twilight hours, when the boundary between worlds grows thin, the old guardian stood watch at the edge of the Whispering Forest.

"Another night," he muttered, gripping his staff. The wood was warm beneath his fingers \u2014 enchanted oak, harvested from the heart of the forest a hundred years ago.

The creatures came at dusk. First the small ones \u2014 shadow wisps that darted between the trees like frightened children. Then the larger beasts: dire wolves with eyes like burning coals, their fur matted with frost from the northern wastes.

He raised his staff and spoke the words of binding. Light erupted from the crystal at its tip, forming a barrier of shimmering gold across the forest path.

"You shall not pass," he whispered. "Not tonight. Not ever."

The wolves howled their frustration and retreated into the darkness. The guardian allowed himself a small smile. Tomorrow would bring new challenges, but tonight, the village was safe.
""")
print(f'txt: {txt_path}')
print(f'\nAll files in: {outdir}')
