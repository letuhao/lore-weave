"""XML-safe text sanitisation for memory-block construction.

Every piece of user-authored content that ends up inside an XML element
MUST pass through sanitize_for_xml() before being concatenated into the
output. No exceptions. The module's __all__ list is the enforcement
point — import the two exported names, never touch the helpers.

Why we do this:

  1. Control characters (U+0000..U+001F except \\t \\n \\r) are illegal
     in XML 1.0 content. A user's bio with a raw U+0001 would break the
     chat-service's XML parser downstream.
  2. `< > & " '` need entity escaping so the LLM sees the actual
     characters the user wrote, not structural XML delimiters.
  3. `]]>` is inherently defanged because html.escape escapes every
     `>` to `&gt;` — so a literal `]]>` sequence cannot survive.
  4. CJK is safe: html.escape leaves multi-byte characters alone.

Keep this module minimal and audited. No imports beyond stdlib.
"""

import html
import re

__all__ = ["sanitize_for_xml", "xml_escape"]

# Characters forbidden or discouraged inside XML element content:
#   * U+0000..U+001F except \t, \n, \r     — C0 controls (XML 1.0 illegal)
#   * U+007F..U+009F                        — DEL + C1 controls (valid but ugly)
#   * U+D800..U+DFFF                        — lone surrogates (XML illegal)
#   * U+FFFE, U+FFFF                        — Unicode noncharacters (XML illegal)
#
# Python strings can legally contain surrogates (from decoding bytes with
# surrogateescape, or from malformed clipboard paste), so we have to strip
# them here or downstream xml.etree.ElementTree will raise
# `ValueError: All strings must be XML compatible`.
_FORBIDDEN_CHARS = re.compile(
    "["
    "\x00-\x08\x0b\x0c\x0e-\x1f"
    "\x7f-\x9f"
    "\ud800-\udfff"
    "\ufffe\uffff"
    "]"
)


def sanitize_for_xml(text: str | None) -> str:
    """Return `text` with all control chars stripped and all
    XML-structural characters entity-escaped.

    None → "" (callers can unconditionally concatenate the result).
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    # 1. Strip all forbidden characters FIRST so their escaped form
    #    doesn't survive as `&#x01;` or similar in the output.
    cleaned = _FORBIDDEN_CHARS.sub("", text)
    # 2. html.escape handles < > & " ' (with quote=True). Because every
    #    `>` becomes `&gt;`, a literal `]]>` sequence cannot appear in
    #    the output — no separate CDATA-defang step needed.
    return html.escape(cleaned, quote=True)


def xml_escape(text: str | None) -> str:
    """Alias for sanitize_for_xml kept for readability in formatters.

    Use xml_escape() when wrapping a single attribute value; use
    sanitize_for_xml() when wrapping multi-line user-authored content.
    Today they behave identically; the split exists so a future version
    can give attribute values a tighter profile.
    """
    return sanitize_for_xml(text)
