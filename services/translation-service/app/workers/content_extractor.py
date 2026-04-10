def extract_content(output: dict) -> str:
    """
    Extract translated text from provider-registry invoke output.

    OpenAI / LM Studio:  output = {"choices": [{"message": {"content": "..."}}]}
    Reasoning models:    output = {"choices": [{"message": {"content": "", "reasoning_content": "..."}}]}
    Anthropic:           output = {"content": [{"type": "text", "text": "..."}]}
    Ollama chat:         output = {"message": {"content": "..."}}
    Raw string content:  output = {"content": "..."}
    """
    choices = output.get("choices")
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") or {}
        content = msg.get("content") or ""
        if content:
            return content
        # Reasoning models may put everything in reasoning_content when content is empty
        reasoning = msg.get("reasoning_content") or ""
        if reasoning:
            return reasoning
        return ""

    content = output.get("content")
    if isinstance(content, list) and content:
        return content[0].get("text") or ""

    message = output.get("message")
    if isinstance(message, dict):
        return message.get("content") or ""

    if isinstance(content, str):
        return content

    raise ValueError(f"Unknown invoke output format. Top-level keys: {list(output.keys())}")
