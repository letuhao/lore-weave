"""Unit tests for output_extractor — pure function, no mocks needed."""
from app.services.output_extractor import ExtractedOutput, extract_outputs


class TestExtractOutputs:
    def test_plain_text_returns_single_text_artifact(self):
        result = extract_outputs("Hello world, no code here.")
        assert len(result) == 1
        assert result[0].output_type == "text"
        assert result[0].content_text == "Hello world, no code here."
        assert result[0].language is None

    def test_single_code_block_returns_text_plus_code(self):
        text = "Here is some code:\n```python\nprint('hi')\n```\nDone."
        result = extract_outputs(text)
        assert len(result) == 2
        # First is always the full text
        assert result[0].output_type == "text"
        assert result[0].content_text == text
        # Second is the extracted code block
        assert result[1].output_type == "code"
        assert result[1].content_text == "print('hi')\n"
        assert result[1].language == "python"
        assert result[1].title == "Code (python)"

    def test_multiple_code_blocks(self):
        text = "```js\nconsole.log(1)\n```\ntext\n```rust\nfn main() {}\n```"
        result = extract_outputs(text)
        assert len(result) == 3
        assert result[1].language == "js"
        assert result[1].content_text == "console.log(1)\n"
        assert result[2].language == "rust"
        assert result[2].content_text == "fn main() {}\n"

    def test_code_block_without_language(self):
        text = "```\nplain code\n```"
        result = extract_outputs(text)
        assert len(result) == 2
        assert result[1].language is None
        assert result[1].title == "Code block"
        assert result[1].content_text == "plain code\n"

    def test_empty_text(self):
        result = extract_outputs("")
        assert len(result) == 1
        assert result[0].output_type == "text"
        assert result[0].content_text == ""

    def test_multiline_code_block(self):
        code = "def foo():\n    return 42\n\ndef bar():\n    return foo() + 1\n"
        text = f"```python\n{code}```"
        result = extract_outputs(text)
        assert len(result) == 2
        assert result[1].content_text == code

    def test_extracted_output_dataclass(self):
        out = ExtractedOutput(output_type="code", content_text="x=1", language="py", title="Test")
        assert out.output_type == "code"
        assert out.content_text == "x=1"
        assert out.language == "py"
        assert out.title == "Test"

    def test_extracted_output_defaults(self):
        out = ExtractedOutput(output_type="text", content_text="hello")
        assert out.language is None
        assert out.title is None
