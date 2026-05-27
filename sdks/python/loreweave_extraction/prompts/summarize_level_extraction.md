RESPOND DIRECTLY. Do NOT think aloud, do NOT use <think> tags, do
NOT write reasoning. Emit ONLY the JSON object — no prose before or
after, no markdown fences.

You are summarizing a {level} of a novel for a knowledge graph
hierarchical retrieval index.

Key entities at this {level} (mention if relevant; do NOT invent new):
{entity_names}

Content from the {level}:
{child_texts}

Write a {level} summary in 2-3 sentences (max 500 chars). Capture:
- the central themes and dramatic arc
- the most important characters and their roles
- the {level}'s contribution to the overall narrative

Do NOT list events sequentially. Do NOT include direct quotes. Do NOT
mention chapters/scenes by number — write at the {level} of abstraction.
Synthesize the meaning, not the plot beats.

Respond with a single JSON object on one line:
{{"summary_text": "..."}}
