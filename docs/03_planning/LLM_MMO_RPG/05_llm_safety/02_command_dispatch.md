<!-- CHUNK-META
source: 05_LLM_SAFETY_LAYER.ARCHIVED.md
chunk: 02_command_dispatch.md
byte_range: 2703-5216
sha256: 25f27c434ded65acc34e75639671c44cc45dcdb4f9778901b72e3d3d450d9400
generated_by: scripts/chunk_doc.py
-->

## 3. Command dispatch (A5)

### 3.1 Syntax (A5-D2)

`/verb target [args]` — classic MUD pattern. Examples:

```
/take map
/drop sword
/attack guard
/give elena coin
/hide
/move north
/look east
/whisper elena "meet me at dawn"
```

Syntax is **deterministic and parseable**. No LLM involvement in command recognition or validation.

### 3.2 Dispatch pipeline (A5-D2)

```
Client sends /verb args
        │
        ▼
  world-service.command_dispatch(pc_id, reality_id, verb, args)
        │
        ├─ Validate (verb exists? PC has permission? target exists? target reachable?)
        │   └─ Invalid → return error to client, NO LLM call
        │
        ├─ Apply deterministically (write L3 event, update projection per R7 single-writer)
        │   └─ Failure → revert, error to client
        │
        └─ Success → emit `session.action_resolved` event
                      │
                      ▼
              LLM narration prompt (persona + action + result + retrieval)
                      │
                      ▼
              Output filter (A6-D4) → narrated response to client
```

State write happens **before** narration. If narration fails or is blocked, state is still correct.

### 3.3 LLM tool-calls — allowed vs forbidden (A5-D3)

The LLM *may* emit tool calls for **non-mutating flavor actions**:

| Allowed (flavor) | Forbidden (state-changing) |
|---|---|
| `whisper(target, content)` | `take(item)` |
| `gesture(type, target)` | `drop(item)` |
| `reveal_emotion(emotion)` | `attack(target)` |
| `look_at(target)` | `heal(target)` |
| `recall_memory(topic)` | `move(direction)` |
|  | `kill(target)` |
|  | `give(item, target)` |
|  | Any inventory / world-state / HP / relationship mutation |

Hard rule: **state-changing actions MUST come from client `/verb` commands, NEVER from LLM tool calls.** This is architecturally enforced — world-service rejects state-mutation tool calls from the LLM pipeline.

### 3.4 Tool-call failure policy (A5-D4)

If an allowed flavor tool-call fails (parse error, invalid args, target gone):

1. Revert any partial effect
2. Log `npc.tool_call_failed` audit event with `(npc_id, pc_id, tool_name, args, error)`
3. Narrator acknowledges with fallback prose: *"Elena seems distracted."* / *"Elena trails off mid-thought."*
4. Do not retry; do not expose the failure reason to the player

Never leave partial state.

---

