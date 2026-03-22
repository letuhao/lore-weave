def extract_content(output: dict) -> str:
    """
    Extract translated text from provider-registry invoke output.

    OpenAI / LM Studio:  output = {"choices": [{"message": {"content": "..."}}]}
    Anthropic:           output = {"content": [{"type": "text", "text": "..."}]}
    Ollama chat:         output = {"message": {"content": "..."}}
    Raw string content:  output = {"content": "..."}
    """
    choices = output.get("choices")
    if isinstance(choices, list) and choices:
        return (choices[0].get("message") or {}).get("content") or ""

    content = output.get("content")
    if isinstance(content, list) and content:
        return content[0].get("text") or ""

    message = output.get("message")
    if isinstance(message, dict):
        return message.get("content") or ""

    if isinstance(content, str):
        return content

    raise ValueError(f"Unknown invoke output format. Top-level keys: {list(output.keys())}")
