"""Extract structured output artifacts from a completed assistant response."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ExtractedOutput:
    output_type: str           # 'text' | 'code'
    content_text: str
    language: str | None = None
    title: str | None = None


_CODE_BLOCK = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)


def extract_outputs(full_text: str) -> list[ExtractedOutput]:
    """Return list of output artifacts for a completed response.

    Always returns the full response as a 'text' artifact.
    Additionally returns each fenced code block as a separate 'code' artifact.
    """
    results: list[ExtractedOutput] = [
        ExtractedOutput(output_type="text", content_text=full_text)
    ]

    for match in _CODE_BLOCK.finditer(full_text):
        lang = match.group(1).strip() or None
        code = match.group(2)
        results.append(
            ExtractedOutput(
                output_type="code",
                content_text=code,
                language=lang,
                title=f"Code ({lang})" if lang else "Code block",
            )
        )

    return results
