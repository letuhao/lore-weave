"""K21 — LLM-callable memory tools.

`definitions` holds the OpenAI function-calling schemas + per-tool
Pydantic argument models; `executor` dispatches a validated tool call
to the knowledge-service repos. The chat-service tool-calling loop
(K21 Cycle B) reaches these only through `POST /internal/tools/execute`.
"""
