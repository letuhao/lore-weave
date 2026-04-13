from app.context.formatters.xml_escape import sanitize_for_xml, xml_escape


def test_none_becomes_empty():
    assert sanitize_for_xml(None) == ""


def test_empty_string():
    assert sanitize_for_xml("") == ""


def test_plain_ascii_roundtrip():
    assert sanitize_for_xml("hello world") == "hello world"


def test_less_than_greater_than_escaped():
    assert sanitize_for_xml("<tag>") == "&lt;tag&gt;"


def test_ampersand_escaped():
    assert sanitize_for_xml("a & b") == "a &amp; b"


def test_double_quote_escaped():
    assert sanitize_for_xml('she said "hi"') == "she said &quot;hi&quot;"


def test_single_quote_escaped():
    # html.escape with quote=True escapes apostrophes to &#x27;
    assert sanitize_for_xml("it's fine") == "it&#x27;s fine"


def test_mixed_xml_chars():
    assert sanitize_for_xml("<a href=\"x&y\">") == "&lt;a href=&quot;x&amp;y&quot;&gt;"


def test_cjk_untouched():
    assert sanitize_for_xml("一位神秘的刀客") == "一位神秘的刀客"


def test_cjk_with_xml_char():
    assert sanitize_for_xml("李雲 & 王小明") == "李雲 &amp; 王小明"


def test_control_character_stripped():
    # U+0001 is illegal in XML 1.0 content → must be removed, not escaped.
    assert sanitize_for_xml("before\x01after") == "beforeafter"


def test_multiple_control_chars_stripped():
    # Strip all C0 controls except tab, newline, CR.
    assert sanitize_for_xml("\x00\x01\x02hello\x03") == "hello"


def test_tab_newline_carriage_return_preserved():
    assert sanitize_for_xml("line1\n\tline2\r\nline3") == "line1\n\tline2\r\nline3"


def test_del_and_c1_controls_stripped():
    # U+007F and U+0080..U+009F — technically valid in XML but ugly.
    assert sanitize_for_xml("a\x7fb\x9fc") == "abc"


def test_cdata_terminator_defanged():
    # The `]]>` sequence shouldn't appear in output even though we
    # don't use CDATA today.
    got = sanitize_for_xml("]]>")
    assert "]]>" not in got
    assert "&gt;" in got


def test_cdata_inside_content():
    got = sanitize_for_xml("hello ]]> world")
    assert "]]>" not in got


def test_non_string_coerced_to_string():
    assert sanitize_for_xml(42) == "42"  # type: ignore[arg-type]


def test_escape_is_idempotent_for_safe_text():
    safe = "already safe text"
    assert sanitize_for_xml(safe) == safe


def test_lone_high_surrogate_stripped():
    # K4a-I1: a lone high surrogate (e.g. from surrogateescape-decoded
    # bytes or malformed clipboard paste) is forbidden in XML content.
    got = sanitize_for_xml("before\ud800after")
    assert got == "beforeafter"


def test_lone_low_surrogate_stripped():
    got = sanitize_for_xml("before\udc00after")
    assert got == "beforeafter"


def test_surrogate_range_stripped():
    # Any codepoint in U+D800..U+DFFF must be removed.
    for cp in (0xD800, 0xD900, 0xDFFF):
        assert sanitize_for_xml(chr(cp)) == ""


def test_unicode_noncharacters_stripped():
    # K4a-I2: U+FFFE and U+FFFF are Unicode noncharacters forbidden in
    # XML content.
    assert sanitize_for_xml("a\ufffeb\uffffc") == "abc"


def test_surrogate_result_parses_as_xml():
    # Regression for the core motivation of K4a-I1: downstream
    # xml.etree.ElementTree must be able to parse whatever we emit.
    import xml.etree.ElementTree as ET

    wrapped = f"<root>{sanitize_for_xml('bad\ud800data')}</root>"
    root = ET.fromstring(wrapped)
    assert root.text == "baddata"


def test_xml_escape_alias_matches_sanitize():
    samples = ["", "plain", "<tag>", "&", "CJK 李雲", None]
    for s in samples:
        assert xml_escape(s) == sanitize_for_xml(s)
