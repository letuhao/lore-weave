# Async Job & Real-Time Event Architecture

## Document Metadata

- **Document ID:** LW-70
- **Version:** 3.2.0
- **Status:** Approved
- **Owner:** Solution Architect + Backend Lead
- **Last Updated:** 2026-03-22
- **Approved By:** Decision Authority
- **Approved Date:** 2026-03-22
- **Summary:** Replace polling-based job monitoring with RabbitMQ message broker for job dispatch/worker scaling, and WebSocket push for real-time frontend updates. Fixes M04 bugs B1–B3 and establishes a reusable async job pattern for all future services.

## Change History

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 3.2.0 | 2026-03-22 | Fix remaining 🟡 issues: coordinator fan-out idempotency, bounded transient requeue (x-retry-count), NestJS AMQP auto-reconnect, WS reconnect state gap (onReconnect) | Assistant |
| 3.1.0 | 2026-03-22 | Architecture review fixes: idempotent `_fail_chapter`, JWT 4h TTL, single AMQP connection, transient/permanent error split, atomic finalization SQL, operational notes | Assistant |
| 3.0.0 | 2026-03-22 | Two-queue fan-out pattern (coordinator + chapter workers), `read=None` timeout, HTTP streaming for long AI calls, per-chapter parallelism | Assistant |
| 2.0.0 | 2026-03-22 | RabbitMQ + WebSocket architecture replacing Postgres NOTIFY | Assistant |
| 1.0.0 | 2026-03-22 | Initial draft: Postgres NOTIFY + WebSocket (rejected) | Assistant |

---

## 1) Problem Statement

### 1.1 Current Bugs (M04 post-implementation review)

| # | Bug | Root Cause |
|---|-----|-----------|
| B1 | 1 chapter selected but both submitted | `jobs` in `useEffect` deps — pre-selection re-fires after `onJobCreated()`, resets `selectedIds` to all chapters |
| B2 | Provider succeeds but runner crashes | `resp["output"]["content"]` — LM Studio/OpenAI returns `choices[0].message.content`; `KeyError` at root |
| B3 | Job stuck `running` forever | `FastAPI.BackgroundTasks` swallows unhandled `KeyError`; job never reaches terminal state |

### 1.2 Why Polling Is Wrong

```
Current: client polls every 5 seconds

FE ──GET /jobs/{id}──► translation-service ──SELECT──► DB   (nothing changed)
FE ──GET /jobs/{id}──► translation-service ──SELECT──► DB   (5s later, nothing changed)
...
```

N users × M jobs × every 5 seconds = wasted DB reads, 5-second lag, no scalability.

### 1.3 Why a Single Worker Queue Is Wrong for Long AI Calls

AI model responses take **30 seconds to 1 hour** in normal operation. In v2.0 the worker called `/invoke` and waited synchronously:

```
Worker-1 (prefetch=1):
  chapter-1: wait 1 hour → done
  chapter-2: wait 1 hour → done     total: 3 hours for 3 chapters
  chapter-3: wait 1 hour → done

Other jobs: queued behind this one job
```

Additional problems in v2.0:
- `timeout=60` in httpx kills any call longer than 60 seconds
- Sequential chapters — no parallelism within a job
- One slow chapter blocks all other jobs on that worker

---

## 2) Architecture Overview

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                    RabbitMQ                             │
                    │                                                         │
                    │  Exchange: loreweave.jobs (direct)                      │
                    │    Queue: translation.jobs  ──────────► coordinator     │
                    │    Queue: translation.chapters  ───────► chapter-worker │
                    │    Queue: translation.chapters.dlq  (dead-letter)       │
                    │                                                         │
                    │  Exchange: loreweave.events (topic)                     │
                    │    routing key: user.<userId>                           │
                    │    Queue: gw.events.<instanceId>  ────► gateway (WS)   │
                    └─────────────────────────────────────────────────────────┘
                              ▲                      ▲
                              │ publish               │ publish events
                    ┌─────────┴──────────┐  ┌────────┴───────────────────┐
                    │ translation-service │  │   translation-worker       │
                    │ (API — thin)        │  │   (two roles, see §4)      │
                    │ POST /jobs          │  │   - job coordinator        │
                    │ → INSERT DB         │  │   - chapter worker         │
                    │ → publish job msg   │  └────────────────────────────┘
                    └─────────────────────┘
                                                        │ WS forward
                    ┌─────────────────────────────────► │
                    │  api-gateway-bff (NestJS)          │
                    │  WebSocket /ws?token=<jwt>         │
                    │  AMQP consumer: gw.events.*        │
                    └───────────────────────────────────►│
                                                         ▼
                                                      Browser
                                                   useJobEvents hook
```

### 2.1 Design Principles

1. **API is thin** — validate, write DB, publish one message, return fast (< 200ms)
2. **Job coordinator** — fast worker: receives job message, publishes N chapter messages, done
3. **Chapter workers** — heavy workers: one message = one AI call; can run for 1 hour; scale independently
4. **AI call never times out on read** — `read` timeout is `None`; only `connect` timeout is strict
5. **All chapters run in parallel** — N chapter messages processed by N workers simultaneously
6. **Gateway is a WebSocket bridge** — subscribes to RabbitMQ events, pushes to connected browsers
7. **Every job type follows the same pattern** — translation today, same infra for any future job

---

## 3) RabbitMQ Topology

### 3.1 Exchanges

| Exchange | Type | Durable | Purpose |
|----------|------|---------|---------|
| `loreweave.jobs` | direct | yes | Job and chapter dispatch |
| `loreweave.events` | topic | yes | Event fan-out to gateway |

### 3.2 Queues

| Queue | Exchange | Routing key | Consumer | Purpose |
|-------|----------|-------------|----------|---------|
| `translation.jobs` | `loreweave.jobs` | `translation.job` | job coordinator | One message per translation job |
| `translation.chapters` | `loreweave.jobs` | `translation.chapter` | chapter worker(s) | One message per chapter |
| `translation.chapters.dlq` | *(default)* | `translation.chapters.dlq` | — | Dead-letter for chapter failures |
| `gw.events.<instanceId>` | `loreweave.events` | `user.#` | gateway instance | Per-instance WS delivery |

Queue properties:
- `translation.jobs`: durable, no DLQ (coordinator is idempotent and fast)
- `translation.chapters`: durable, `x-dead-letter-exchange=""`, `x-dead-letter-routing-key="translation.chapters.dlq"`, `x-message-ttl=86400000` (24h — covers 1-hour AI calls with margin)
- `translation.chapters.dlq`: durable — inspectable, not auto-requeued
- `gw.events.<instanceId>`: non-durable, exclusive, auto-delete

### 3.3 Message: Job Dispatch (API → `translation.job`)

```json
{
  "job_id":          "uuid",
  "user_id":         "uuid",
  "book_id":         "uuid",
  "chapter_ids":     ["uuid", "uuid", "..."],
  "model_source":    "user_model",
  "model_ref":       "uuid",
  "system_prompt":   "...",
  "user_prompt_tpl": "...",
  "target_language": "en"
}
```

AMQP: `delivery_mode=2` (persistent), `content_type=application/json`

### 3.4 Message: Chapter Dispatch (coordinator → `translation.chapter`)

Each chapter gets its own self-contained message. The chapter worker needs nothing else to do its work.

```json
{
  "job_id":          "uuid",
  "chapter_id":      "uuid",
  "chapter_index":   0,
  "total_chapters":  10,
  "book_id":         "uuid",
  "user_id":         "uuid",
  "model_source":    "user_model",
  "model_ref":       "uuid",
  "system_prompt":   "...",
  "user_prompt_tpl": "...",
  "target_language": "en"
}
```

AMQP: `delivery_mode=2`, `content_type=application/json`

### 3.5 Message: Event (`loreweave.events`, routing key `user.<userId>`)

```json
{
  "event":    "job.status_changed",
  "job_id":   "uuid",
  "job_type": "translation",
  "user_id":  "uuid",
  "payload":  {}
}
```

#### Event types

| `event` | `payload` fields | emitted by | when |
|---------|-----------------|-----------|------|
| `job.created` | `book_id, total_chapters, status` | API service | job row inserted |
| `job.status_changed` | `status, completed_chapters, failed_chapters` | chapter worker | job transitions (running → completed/partial/failed) |
| `job.chapter_done` | `chapter_id, chapter_index, total_chapters, status, error_message?` | chapter worker | each chapter finishes |
| `job.error` | `error_code, detail` | any worker | unrecoverable crash |

---

## 4) Worker Roles

### 4.1 Job Coordinator Worker

**Queue:** `translation.jobs` | **Prefetch:** 1 | **Expected duration:** < 1 second per message

Responsibility: receive the job message, fan out one chapter message per chapter, mark job as `running`.

```
receive job message
  │
  ├─ UPDATE translation_jobs SET status='running'
  ├─ for each chapter_id:
  │    publish chapter message → translation.chapters
  ├─ publish event: job.status_changed (status=running)
  └─ ack message
```

This worker is fast. It never calls external services. Multiple coordinators can run but `prefetch=1` is fine since each message takes < 1 second.

### 4.2 Chapter Worker

**Queue:** `translation.chapters` | **Prefetch:** 1 | **Expected duration:** 30 seconds – 1 hour per message

Responsibility: process exactly one chapter. Call the AI model. Update DB. Emit events. Check if the parent job is now complete.

```
receive chapter message
  │
  ├─ check job cancelled → if yes, mark chapter cancelled, ack, return
  ├─ UPDATE chapter_translations SET status='running'
  ├─ GET chapter body from book-service
  ├─ POST /invoke (AI call — may take 1 hour, read timeout = None)
  │     stream response tokens as they arrive
  ├─ UPDATE chapter_translations SET status='completed', translated_body=...
  ├─ increment translation_jobs.completed_chapters
  ├─ publish event: job.chapter_done
  ├─ check if all chapters for this job are terminal
  │     if yes → UPDATE translation_jobs SET status=completed/partial/failed
  │              publish event: job.status_changed (final status)
  └─ ack message

on any unhandled exception:
  ├─ UPDATE chapter_translations SET status='failed'
  ├─ increment translation_jobs.failed_chapters
  ├─ publish event: job.chapter_done (status=failed)
  ├─ check if all chapters terminal → finalize job if so
  ├─ nack (requeue=False) → message goes to DLQ
  └─ raise
```

**"All chapters terminal" check:** after every chapter completion (success or failure), the chapter worker queries:

```sql
SELECT
  total_chapters,
  completed_chapters,
  failed_chapters
FROM translation_jobs
WHERE job_id = $1
```

If `completed_chapters + failed_chapters == total_chapters` the job is done. The first worker to satisfy this condition writes the final status. This is safe because the counters are incremented atomically (`completed_chapters = completed_chapters + 1`) and the final status write is idempotent (only transitions from `running`).

### 4.3 Why Not One Worker Doing Both Roles

Keeping coordinator and chapter worker as separate queue consumers allows:
- Running more chapter workers than coordinators (coordinators are cheap)
- Coordinator failures do not affect in-flight chapter workers
- Clear separation of concern

In practice they can be **the same Python process** listening to both queues — just two consumers on one AMQP channel. Or two separate deployed containers. The docker-compose scales them independently.

---

## 5) HTTP Timeout Strategy for Long AI Calls

```python
# Chapter worker HTTP client
httpx.AsyncClient(
    timeout=httpx.Timeout(
        connect=10.0,   # fail fast if provider unreachable
        write=30.0,     # fail fast if we can't send the request
        read=None,      # NO read timeout — AI can take 1 hour
        pool=5.0,
    )
)
```

### Why `read=None` is safe here

- The AI model is actively computing — TCP connection is alive, not idle
- Intermediate proxies (nginx, gateway) only kill truly idle connections
- The worker's asyncio event loop is not blocked — AMQP heartbeats continue during the `await`
- If the connection drops mid-response, `httpx` raises `httpx.RemoteProtocolError` → chapter marked failed → DLQ

### Streaming (preferred for models that support it)

If the provider supports SSE/chunked streaming (`stream=True` in httpx), the worker reads tokens as they arrive:

```python
async with client.stream("POST", ".../invoke", json=payload, headers=headers) as response:
    buffer = []
    async for chunk in response.aiter_text():
        buffer.append(chunk)
        # Could emit incremental events here in the future
    translated_body = "".join(buffer)
```

Benefits:
- TCP connection stays active (data flowing) → no proxy idle timeout
- No single large response buffered in memory
- Future: emit `job.chapter_progress` events with partial text

Non-streaming fallback (for models that do not support streaming):
```python
r = await client.post(".../invoke", json=payload, headers=headers)
```
With `read=None`, this waits however long the model needs.

### RabbitMQ heartbeat during long AI calls

`aio_pika` runs AMQP heartbeats on the asyncio event loop background. While the chapter worker `await`s the AI response, the event loop is free to handle heartbeats. RabbitMQ will not consider the connection dead.

The chapter message is not acked until the AI call completes, which means RabbitMQ holds the message as "unacknowledged" for the duration. This is correct behavior — `consumer_timeout` in RabbitMQ is disabled by default, so unacknowledged messages are not redelivered while the connection is alive.

---

## 6) Services: What Changes

### 6.1 translation-service (API — no more BackgroundTasks)

Becomes thin: validate, write DB, publish one message, return 201.

#### `app/broker.py` (new)

```python
import json, aio_pika
from .config import settings

_connection = None
_channel    = None

def get_channel() -> aio_pika.Channel:
    """Return the shared channel for use by worker consumers."""
    if _channel is None:
        raise RuntimeError("Broker not connected — call connect_broker() first")
    return _channel

async def connect_broker():
    global _connection, _channel
    _connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    _channel    = await _connection.channel()

    jobs_exchange = await _channel.declare_exchange(
        "loreweave.jobs", aio_pika.ExchangeType.DIRECT, durable=True
    )
    await _channel.declare_exchange(
        "loreweave.events", aio_pika.ExchangeType.TOPIC, durable=True
    )
    await _channel.declare_queue(
        "translation.jobs", durable=True
    )
    await _channel.declare_queue(
        "translation.chapters",
        durable=True,
        arguments={
            "x-dead-letter-exchange":    "",
            "x-dead-letter-routing-key": "translation.chapters.dlq",
            "x-message-ttl":             86_400_000,  # 24h
        },
    )
    await _channel.declare_queue("translation.chapters.dlq", durable=True)

async def publish(routing_key: str, body: dict):
    exchange = await _channel.get_exchange("loreweave.jobs")
    await exchange.publish(
        aio_pika.Message(
            body=json.dumps(body).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
        ),
        routing_key=routing_key,
    )

async def publish_event(user_id: str, event: dict):
    exchange = await _channel.get_exchange("loreweave.events")
    await exchange.publish(
        aio_pika.Message(
            body=json.dumps({**event, "user_id": user_id}).encode(),
            content_type="application/json",
        ),
        routing_key=f"user.{user_id}",
    )

async def close_broker():
    if _connection:
        await _connection.close()
```

#### `routers/jobs.py` — publish after DB insert

```python
await publish("translation.job", {
    "job_id":          str(job_id),
    "user_id":         user_id,
    "book_id":         str(book_id),
    "chapter_ids":     [str(c) for c in chapter_ids],
    "model_source":    eff["model_source"],
    "model_ref":       str(eff["model_ref"]),
    "system_prompt":   eff["system_prompt"],
    "user_prompt_tpl": eff["user_prompt_tpl"],
    "target_language": eff["target_language"],
})
await publish_event(user_id, {
    "event":    "job.created",
    "job_id":   str(job_id),
    "job_type": "translation",
    "payload":  {"book_id": str(book_id), "total_chapters": len(chapter_ids), "status": "pending"},
})
```

#### `requirements.txt` additions

```
aio_pika>=9.4
```

---

### 6.2 translation-worker (new service — two consumers, one process)

Single Python process consuming from **both** queues. The coordinator consumer is fast; the chapter consumer is long-running.

#### File structure

```
services/translation-service/
  worker.py                         ← entry point
  Dockerfile.worker                 ← CMD: python worker.py
  app/
    broker.py                       ← shared with API
    config.py                       ← shared (add rabbitmq_url)
    database.py                     ← shared
    auth.py                         ← shared
    workers/
      coordinator.py                ← handles translation.jobs queue
      chapter_worker.py             ← handles translation.chapters queue
      content_extractor.py          ← _extract_content() — B2 fix
```

#### `worker.py`

```python
import asyncio
import json
import aio_pika
from app.config import settings
from app.database import init_pool, get_pool
from app.broker import connect_broker, get_channel, publish, publish_event
from app.workers.coordinator import handle_job_message
from app.workers.chapter_worker import handle_chapter_message, is_transient_error


async def main():
    await init_pool(settings.database_url)
    await connect_broker()

    # Reuse the channel opened by connect_broker() — no second connection
    channel = get_channel()
    await channel.set_qos(prefetch_count=1)

    job_queue     = await channel.get_queue("translation.jobs")
    chapter_queue = await channel.get_queue("translation.chapters")

    async def on_job(message: aio_pika.IncomingMessage):
        # Coordinator is fast and idempotent — requeue on failure so it retries
        async with message.process(requeue=True):
            await handle_job_message(json.loads(message.body), get_pool(), publish, publish_event)

    MAX_TRANSIENT_RETRIES = 5

    async def on_chapter(message: aio_pika.IncomingMessage):
        body = json.loads(message.body)
        try:
            await handle_chapter_message(body, get_pool(), publish_event)
            await message.ack()
        except Exception as exc:
            if is_transient_error(exc):
                # Bounded retry: cap transient retries so a persistent infra outage
                # (e.g. book-service down for 30 min) does not cause an infinite
                # tight retry loop consuming all worker capacity.
                retries = int((message.headers or {}).get('x-retry-count', 0))
                if retries >= MAX_TRANSIENT_RETRIES:
                    # Give up after 5 transient retries → DLQ for inspection
                    await message.nack(requeue=False)
                else:
                    # Republish with incremented counter instead of raw requeue
                    # (raw requeue puts the message at the front with the old headers)
                    new_headers = dict(message.headers or {})
                    new_headers['x-retry-count'] = retries + 1
                    channel = get_channel()
                    jobs_exchange = await channel.get_exchange("loreweave.jobs")
                    await jobs_exchange.publish(
                        aio_pika.Message(
                            body=message.body,
                            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                            content_type="application/json",
                            headers=new_headers,
                        ),
                        routing_key="translation.chapter",
                    )
                    await message.ack()  # ack original; new message is the retry
            else:
                # Permanent: unrecoverable logic error — send to DLQ
                await message.nack(requeue=False)

    await job_queue.consume(on_job)
    await chapter_queue.consume(on_chapter)

    await asyncio.Future()   # run forever


if __name__ == "__main__":
    asyncio.run(main())
```

#### `app/workers/coordinator.py`

```python
import json
from uuid import UUID


async def handle_job_message(msg: dict, pool, publish, publish_event):
    job_id  = UUID(msg["job_id"])
    user_id = msg["user_id"]

    async with pool.acquire() as db:
        # Idempotency guard: if the job is already 'running', it was already
        # fanned out (coordinator crashed mid-publish and was requeued). Ack
        # and return — do not publish duplicate chapter messages.
        status = await db.fetchval(
            "SELECT status FROM translation_jobs WHERE job_id=$1", job_id
        )
        if status == 'running':
            return  # already fanned out — caller (on_job) will ack

        await db.execute(
            "UPDATE translation_jobs SET status='running', started_at=now() WHERE job_id=$1",
            job_id,
        )

    # Fan out one message per chapter
    for index, chapter_id in enumerate(msg["chapter_ids"]):
        await publish("translation.chapter", {
            "job_id":          msg["job_id"],
            "chapter_id":      chapter_id,
            "chapter_index":   index,
            "total_chapters":  len(msg["chapter_ids"]),
            "book_id":         msg["book_id"],
            "user_id":         user_id,
            "model_source":    msg["model_source"],
            "model_ref":       msg["model_ref"],
            "system_prompt":   msg["system_prompt"],
            "user_prompt_tpl": msg["user_prompt_tpl"],
            "target_language": msg["target_language"],
        })

    await publish_event(user_id, {
        "event":    "job.status_changed",
        "job_id":   msg["job_id"],
        "job_type": "translation",
        "payload":  {"status": "running", "completed_chapters": 0, "failed_chapters": 0},
    })
```

#### `app/workers/chapter_worker.py`

```python
import time
from uuid import UUID
import httpx
import asyncpg
from app.auth import mint_user_jwt
from app.config import settings
from app.workers.content_extractor import extract_content

# ── Transient vs permanent error classification ───────────────────────────────
#
# Transient: caused by infrastructure blip — safe to requeue for retry
# Permanent: caused by bad data or logic — send to DLQ, do not retry
#
# worker.py uses this to decide: nack(requeue=True) vs nack(requeue=False)

class PermanentJobError(Exception):
    """Unrecoverable error for this chapter — goes to DLQ."""

class TransientJobError(Exception):
    """Infrastructure blip — requeue for retry."""

def is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, TransientJobError):
        return True
    # asyncpg connection failures are transient
    if isinstance(exc, (asyncpg.PostgresConnectionError, asyncpg.TooManyConnectionsError)):
        return True
    # httpx network-level errors (not HTTP 4xx/5xx) are transient
    if isinstance(exc, httpx.NetworkError):
        return True
    return False


async def handle_chapter_message(msg: dict, pool, publish_event):
    job_id     = UUID(msg["job_id"])
    chapter_id = UUID(msg["chapter_id"])
    user_id    = msg["user_id"]

    try:
        await _process_chapter(msg, job_id, chapter_id, user_id, pool, publish_event)
    except (PermanentJobError, Exception) as exc:
        # Only mark chapter failed for permanent errors or unexpected exceptions.
        # Transient errors skip this — the chapter stays 'running' and will be
        # retried when the message is requeued.
        if not is_transient_error(exc):
            await _fail_chapter(pool, job_id, chapter_id, f"internal_error: {exc}")
            await _emit_chapter_done(publish_event, user_id, msg, "failed", f"internal_error: {exc}")
            await _check_job_completion(pool, job_id, user_id, msg, publish_event)
        raise   # worker.py decides requeue vs DLQ based on is_transient_error()


async def _process_chapter(msg, job_id, chapter_id, user_id, pool, publish_event):
    async with pool.acquire() as db:
        cancelled = await db.fetchval(
            "SELECT status = 'cancelled' FROM translation_jobs WHERE job_id=$1", job_id
        )
        if cancelled:
            return

        await db.execute(
            "UPDATE chapter_translations SET status='running', started_at=now() WHERE job_id=$1 AND chapter_id=$2",
            job_id, chapter_id,
        )

    # ── JWT strategy ──────────────────────────────────────────────────────────
    # Mint with TTL = 4 hours (covers max expected AI call duration + buffer).
    # Token is fixed for the lifetime of this chapter call — no mid-stream
    # refresh is possible once streaming begins. The 4h TTL avoids expiry
    # on long-running chapters. If your policy requires shorter tokens, mint
    # a fresh one per chapter and accept a window where the token is ~4h valid.
    token = mint_user_jwt(user_id, settings.jwt_secret, ttl_seconds=14_400)  # 4h

    # read=None: no timeout on AI response — may take up to several hours
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, write=30.0, read=None, pool=5.0)
    ) as client:

        # Fetch chapter body from book-service
        try:
            r = await client.get(
                f"{settings.book_service_internal_url}/internal/books/{msg['book_id']}/chapters/{chapter_id}"
            )
        except httpx.NetworkError as exc:
            raise TransientJobError(f"book-service network error: {exc}") from exc

        if r.status_code == 404:
            # Permanent — chapter does not exist
            await _fail_chapter(pool, job_id, chapter_id, "chapter_not_found")
            await _emit_chapter_done(publish_event, user_id, msg, "failed", "chapter_not_found")
            await _check_job_completion(pool, job_id, user_id, msg, publish_event)
            return
        if r.status_code >= 500:
            raise TransientJobError(f"book-service {r.status_code}")
        r.raise_for_status()

        chapter     = r.json()
        source_lang = chapter.get("original_language") or "unknown"
        user_msg    = msg["user_prompt_tpl"].format_map({
            "source_language": source_lang,
            "target_language": msg["target_language"],
            "chapter_text":    chapter.get("body") or "",
        })

        invoke_payload = {
            "model_source": msg["model_source"],
            "model_ref":    msg["model_ref"],
            "input": {
                "messages": [
                    {"role": "system", "content": msg["system_prompt"]},
                    {"role": "user",   "content": user_msg},
                ]
            },
        }
        headers = {"Authorization": f"Bearer {token}"}

        # Stream the AI response to keep TCP alive during long generation
        try:
            async with client.stream(
                "POST",
                f"{settings.provider_registry_service_url}/v1/model-registry/invoke",
                json=invoke_payload,
                headers=headers,
            ) as resp:
                if resp.status_code == 402:
                    # Permanent — billing rejected
                    await _fail_chapter(pool, job_id, chapter_id, "billing_rejected")
                    await _emit_chapter_done(publish_event, user_id, msg, "failed", "billing_rejected")
                    await _check_job_completion(pool, job_id, user_id, msg, publish_event)
                    return
                if resp.status_code == 401 or resp.status_code == 403:
                    # Should not happen (4h token), but guard it
                    raise PermanentJobError(f"invoke auth error {resp.status_code}")
                if resp.status_code >= 500:
                    raise TransientJobError(f"provider-registry {resp.status_code}")
                resp.raise_for_status()

                raw_chunks = []
                async for chunk in resp.aiter_bytes():
                    raw_chunks.append(chunk)
        except httpx.NetworkError as exc:
            raise TransientJobError(f"invoke network error: {exc}") from exc

        import json as _json
        full_response   = _json.loads(b"".join(raw_chunks))
        translated_body = extract_content(full_response.get("output") or {})
        usage_log_id    = full_response.get("usage_log_id")
        usage           = full_response.get("usage") or {}
        input_tokens    = usage.get("input_tokens")
        output_tokens   = usage.get("output_tokens")

    async with pool.acquire() as db:
        await db.execute(
            """UPDATE chapter_translations SET
                 status='completed', translated_body=$1, source_language=$2,
                 input_tokens=$3, output_tokens=$4, usage_log_id=$5, finished_at=now()
               WHERE job_id=$6 AND chapter_id=$7""",
            translated_body, source_lang, input_tokens, output_tokens,
            UUID(usage_log_id) if usage_log_id else None,
            job_id, chapter_id,
        )
        await db.execute(
            "UPDATE translation_jobs SET completed_chapters=completed_chapters+1 WHERE job_id=$1",
            job_id,
        )

    await _emit_chapter_done(publish_event, user_id, msg, "completed", None)
    await _check_job_completion(pool, job_id, user_id, msg, publish_event)


async def _check_job_completion(pool, job_id, user_id, msg, publish_event):
    """
    Atomically check if all chapters are terminal and finalize job status.

    Uses a single UPDATE with the completion condition in the WHERE clause
    to eliminate the TOCTOU race between SELECT (read counters) and UPDATE
    (write final status). Only the worker whose UPDATE matches wins; others
    see RETURNING = NULL and stay silent.
    """
    async with pool.acquire() as db:
        row = await db.fetchrow(
            """
            UPDATE translation_jobs SET
              status = CASE
                WHEN failed_chapters = 0                THEN 'completed'
                WHEN completed_chapters > 0             THEN 'partial'
                ELSE                                         'failed'
              END,
              finished_at = now()
            WHERE job_id = $1
              AND status  = 'running'
              AND (completed_chapters + failed_chapters) = total_chapters
            RETURNING status, completed_chapters, failed_chapters
            """,
            job_id,
        )

    if row:  # this worker won the race — emit the final event
        await publish_event(user_id, {
            "event":    "job.status_changed",
            "job_id":   str(job_id),
            "job_type": "translation",
            "payload":  {
                "status":             row["status"],
                "completed_chapters": row["completed_chapters"],
                "failed_chapters":    row["failed_chapters"],
            },
        })


async def _fail_chapter(pool, job_id: UUID, chapter_id: UUID, reason: str) -> None:
    """
    Idempotent chapter failure: only increments failed_chapters if the
    chapter was not already in a terminal state. Prevents double-counting
    if an exception is raised after _fail_chapter was already called for
    a known-bad status (e.g. 404, 402).
    """
    async with pool.acquire() as db:
        updated = await db.fetchval(
            """
            UPDATE chapter_translations
            SET status='failed', error_message=$1, finished_at=now()
            WHERE job_id=$2 AND chapter_id=$3 AND status != 'failed'
            RETURNING chapter_id
            """,
            reason, job_id, chapter_id,
        )
        if updated:  # only count if this was the first failure write
            await db.execute(
                "UPDATE translation_jobs SET failed_chapters=failed_chapters+1 WHERE job_id=$1",
                job_id,
            )


async def _emit_chapter_done(publish_event, user_id, msg, status, error_message):
    await publish_event(user_id, {
        "event":    "job.chapter_done",
        "job_id":   msg["job_id"],
        "job_type": "translation",
        "payload":  {
            "chapter_id":     msg["chapter_id"],
            "chapter_index":  msg["chapter_index"],
            "total_chapters": msg["total_chapters"],
            "status":         status,
            "error_message":  error_message,
        },
    })
```

#### `app/workers/content_extractor.py` — B2 fix

```python
def extract_content(output: dict) -> str:
    """
    Extract translated text from provider-registry invoke output.

    OpenAI / LM Studio:  output = { choices: [{message: {content: "..."}}] }
    Anthropic:           output = { content: [{type: "text", text: "..."}] }
    Ollama chat:         output = { message: { content: "..." } }
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

    raise ValueError(f"Unknown output format. Keys: {list(output.keys())}")
```

#### `Dockerfile.worker`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "worker.py"]
```

---

### 6.3 api-gateway-bff — WebSocket + RabbitMQ consumer

Unchanged from v2.0 design. The gateway subscribes to `loreweave.events` exchange with an exclusive auto-delete queue, routes incoming events to connected WebSocket clients by `user_id`.

#### New files

```
services/api-gateway-bff/src/ws/
  amqp.service.ts     ← connect to RabbitMQ, manage per-userId subscriptions
  events.gateway.ts   ← NestJS WebSocket gateway: auth JWT, subscribe/unsubscribe
  ws.module.ts        ← NestJS module
```

#### `amqp.service.ts`

```typescript
import { Injectable, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import * as amqp from 'amqplib';
import { v4 as uuidv4 } from 'uuid';

type EventHandler = (event: object) => void;

@Injectable()
export class AmqpService implements OnModuleInit, OnModuleDestroy {
  private conn: amqp.ChannelModel;
  private channel: amqp.Channel;
  private readonly handlers = new Map<string, Set<EventHandler>>();
  private destroyed = false;

  async onModuleInit() {
    this.conn    = await this.connectWithRetry();
    // Reconnect automatically if RabbitMQ restarts or the connection drops
    this.conn.on('close', () => { if (!this.destroyed) this.onModuleInit(); });
    this.conn.on('error', () => {}); // prevent unhandled rejection; 'close' follows
    this.channel = await this.conn.createChannel();

    await this.channel.assertExchange('loreweave.events', 'topic', { durable: true });

    const queueName = `gw.events.${uuidv4()}`;
    await this.channel.assertQueue(queueName, { exclusive: true, autoDelete: true });
    await this.channel.bindQueue(queueName, 'loreweave.events', 'user.#');

    await this.channel.consume(queueName, (msg) => {
      if (!msg) return;
      try {
        const event  = JSON.parse(msg.content.toString());
        const userId = event.user_id as string;
        this.handlers.get(userId)?.forEach((cb) => cb(event));
      } catch {}
      this.channel.ack(msg);
    });
  }

  private async connectWithRetry(): Promise<amqp.ChannelModel> {
    while (true) {
      try { return await amqp.connect(process.env.RABBITMQ_URL!); }
      catch { await new Promise(r => setTimeout(r, 3000)); }
    }
  }

  subscribe(userId: string, handler: EventHandler): () => void {
    if (!this.handlers.has(userId)) this.handlers.set(userId, new Set());
    this.handlers.get(userId)!.add(handler);
    return () => {
      this.handlers.get(userId)?.delete(handler);
      if (this.handlers.get(userId)?.size === 0) this.handlers.delete(userId);
    };
  }

  async onModuleDestroy() {
    this.destroyed = true;
    await this.channel?.close();
    await this.conn?.close();
  }
}
```

#### `events.gateway.ts`

```typescript
import {
  WebSocketGateway, WebSocketServer,
  OnGatewayConnection, OnGatewayDisconnect,
} from '@nestjs/websockets';
import { Server, WebSocket } from 'ws';
import { IncomingMessage } from 'http';
import * as jwt from 'jsonwebtoken';
import { AmqpService } from './amqp.service';

@WebSocketGateway({ path: '/ws' })
export class EventsGateway implements OnGatewayConnection, OnGatewayDisconnect {
  @WebSocketServer() server: Server;
  constructor(private readonly amqp: AmqpService) {}
  private readonly unsubs = new Map<WebSocket, () => void>();

  handleConnection(socket: WebSocket, req: IncomingMessage) {
    const token = new URL(req.url!, 'http://x').searchParams.get('token');
    if (!token) { socket.close(4001, 'missing_token'); return; }

    let userId: string;
    try {
      userId = (jwt.verify(token, process.env.JWT_SECRET!) as { sub: string }).sub;
    } catch {
      socket.close(4001, 'invalid_token');
      return;
    }

    const unsub = this.amqp.subscribe(userId, (event) => {
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(event));
    });
    this.unsubs.set(socket, unsub);
  }

  handleDisconnect(socket: WebSocket) {
    this.unsubs.get(socket)?.();
    this.unsubs.delete(socket);
  }
}
```

#### `ws.module.ts`

```typescript
import { Module } from '@nestjs/common';
import { AmqpService } from './amqp.service';
import { EventsGateway } from './events.gateway';

@Module({ providers: [AmqpService, EventsGateway] })
export class WsModule {}
```

#### `main.ts` addition

```typescript
import { WsAdapter } from '@nestjs/platform-ws';
app.useWebSocketAdapter(new WsAdapter(app));
```

#### `package.json` additions

```json
"@nestjs/websockets": "^10.x",
"@nestjs/platform-ws": "^10.x",
"ws": "^8.x",
"@types/ws": "^8.x",
"amqplib": "^0.10.x",
"@types/amqplib": "^0.10.x",
"jsonwebtoken": "^9.x",
"@types/jsonwebtoken": "^9.x",
"uuid": "^9.x"
```

---

### 6.4 Infrastructure — docker-compose.yml additions

#### RabbitMQ service

```yaml
rabbitmq:
  image: rabbitmq:3.13-management-alpine
  environment:
    RABBITMQ_DEFAULT_USER: loreweave
    RABBITMQ_DEFAULT_PASS: loreweave_dev
  ports:
    - "5672:5672"
    - "15672:15672"   # management UI
  volumes:
    - loreweave_rabbitmq:/var/lib/rabbitmq
  healthcheck:
    test: ["CMD", "rabbitmq-diagnostics", "ping"]
    interval: 5s
    timeout: 10s
    retries: 10
```

#### translation-worker service

```yaml
translation-worker:
  build:
    context: ../services/translation-service
    dockerfile: Dockerfile.worker
  environment:
    DATABASE_URL: postgresql://loreweave:loreweave_dev@postgres:5432/loreweave_translation
    JWT_SECRET: ${JWT_SECRET:-loreweave_local_dev_jwt_secret_change_me_32chars}
    BOOK_SERVICE_INTERNAL_URL: http://book-service:8082
    PROVIDER_REGISTRY_SERVICE_URL: http://provider-registry-service:8085
    RABBITMQ_URL: amqp://loreweave:loreweave_dev@rabbitmq:5672/
  depends_on:
    postgres:        { condition: service_healthy }
    postgres-db-bootstrap: { condition: service_completed_successfully }
    rabbitmq:        { condition: service_healthy }
    book-service:    { condition: service_healthy }
    provider-registry-service: { condition: service_healthy }
  deploy:
    replicas: 1   # scale up: docker compose up --scale translation-worker=N
```

#### Updated translation-service env

```yaml
translation-service:
  environment:
    # ...existing...
    RABBITMQ_URL: amqp://loreweave:loreweave_dev@rabbitmq:5672/
  depends_on:
    # ...existing...
    rabbitmq: { condition: service_healthy }
```

#### Updated api-gateway-bff env

```yaml
api-gateway-bff:
  environment:
    # ...existing...
    RABBITMQ_URL: amqp://loreweave:loreweave_dev@rabbitmq:5672/
    JWT_SECRET: ${JWT_SECRET:-loreweave_local_dev_jwt_secret_change_me_32chars}
  depends_on:
    # ...existing...
    rabbitmq: { condition: service_healthy }
```

#### New volume

```yaml
volumes:
  loreweave_pg:
  loreweave_minio:
  loreweave_rabbitmq:
```

---

## 7) Frontend Changes

### 7.1 New hook: `frontend/src/hooks/useJobEvents.ts`

```typescript
import { useEffect, useRef } from 'react';
import { useAuth } from '@/auth';

export type JobEvent = {
  event:    string;
  job_id:   string;
  job_type: string;
  user_id:  string;
  payload:  Record<string, unknown>;
};

export function useJobEvents({
  onEvent,
  onReconnect,
  enabled = true,
}: {
  onEvent:      (e: JobEvent) => void;
  /** Called after every successful (re-)connect. Use to re-fetch current job
   *  state so events missed during the reconnect window do not leave the UI
   *  stale. Typically: trigger a fresh GET /jobs/:id. */
  onReconnect?: () => void;
  enabled?:     boolean;
}) {
  const { accessToken } = useAuth();
  const onEventRef     = useRef(onEvent);
  const onReconnectRef = useRef(onReconnect);
  onEventRef.current     = onEvent;
  onReconnectRef.current = onReconnect;

  useEffect(() => {
    if (!enabled || !accessToken) return;
    let dead = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    function connect() {
      if (dead) return;
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const ws = new WebSocket(`${proto}://${location.host}/ws?token=${accessToken}`);

      ws.onopen = () => {
        // Re-sync state on every connect/reconnect to patch any events missed
        // during the reconnect window (e.g. after a token rotation or blip).
        onReconnectRef.current?.();
      };
      ws.onmessage = (e) => {
        try { onEventRef.current(JSON.parse(e.data)); } catch {}
      };
      ws.onclose = (ev) => {
        if (!dead && ev.code !== 4001) timer = setTimeout(connect, 3000);
      };
      ws.onerror = () => ws.close();

      return ws;
    }

    const ws = connect();
    return () => {
      dead = true;
      if (timer) clearTimeout(timer);
      ws?.close();
    };
  }, [accessToken, enabled]);
}
```

### 7.2 Rewrite: `components/translation/TranslateButton.tsx`

Remove all `setInterval` polling. Use `useJobEvents`.

```typescript
export function TranslateButton({ token, bookId, chapterIds, onJobCreated, disabled }: Props) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [job,   setJob]   = useState<TranslationJob | null>(null);
  const [error, setError] = useState('');
  const jobIdRef = useRef<string | null>(null);

  const handleEvent = useCallback((e: JobEvent) => {
    if (!jobIdRef.current || e.job_id !== jobIdRef.current) return;

    if (e.event === 'job.status_changed') {
      const p = e.payload as { status: string; completed_chapters: number; failed_chapters: number };
      setJob((prev) => prev ? { ...prev, ...p } : prev);
      if      (p.status === 'completed') setPhase('done');
      else if (p.status === 'partial')   setPhase('partial');
      else if (p.status === 'failed' || p.status === 'cancelled') {
        setError(p.status);
        setPhase('error');
      }
    }
    if (e.event === 'job.error') {
      setError((e.payload as { detail: string }).detail || 'Unknown error');
      setPhase('error');
    }
  }, []);

  // Re-fetch job on WS reconnect to patch any state missed during the gap
  const handleReconnect = useCallback(async () => {
    if (!jobIdRef.current) return;
    try {
      const latest = await translationApi.getJob(token, jobIdRef.current);
      setJob(latest);
      if      (latest.status === 'completed') setPhase('done');
      else if (latest.status === 'partial')   setPhase('partial');
      else if (latest.status === 'failed' || latest.status === 'cancelled') {
        setError(latest.status); setPhase('error');
      }
    } catch {}
  }, [token]);

  useJobEvents({ onEvent: handleEvent, onReconnect: handleReconnect, enabled: phase === 'polling' });

  async function handleClick() {
    if (!chapterIds.length) return;
    setPhase('submitting');
    setError('');
    try {
      const created    = await translationApi.createJob(token, bookId, { chapter_ids: chapterIds });
      jobIdRef.current = created.job_id;
      setJob(created);
      onJobCreated?.(created);
      setPhase('polling');
    } catch (err: unknown) {
      setError((err as { message?: string })?.message || 'Failed to start translation');
      setPhase('error');
    }
  }
  // ... render (same UI as before, no setInterval code)
}
```

### 7.3 Fix B1: `pages/BookTranslationPage.tsx`

```typescript
// Pre-selection runs once only — never re-runs when jobs update
const preselectedRef = useRef(false);

useEffect(() => {
  if (loadingChapters || loadingJobs) return;
  if (preselectedRef.current) return;
  preselectedRef.current = true;

  const translatedIds = new Set(
    jobs
      .filter((j) => j.status === 'completed' || j.status === 'partial')
      .flatMap((j) => j.chapter_ids),
  );
  const untranslated = chapters
    .filter((c) => !translatedIds.has(c.chapter_id))
    .map((c) => c.chapter_id);
  setSelectedIds(untranslated.length > 0 ? untranslated : chapters.map((c) => c.chapter_id));
}, [loadingChapters, loadingJobs]);  // chapters + jobs intentionally NOT deps

// Page-level subscription keeps Recent Jobs list live
const handleJobEvent = useCallback((e: JobEvent) => {
  if (e.job_type !== 'translation') return;
  if (e.event === 'job.status_changed' || e.event === 'job.chapter_done') {
    setJobs((prev) =>
      prev.map((j) =>
        j.job_id === e.job_id ? { ...j, ...(e.payload as Partial<TranslationJob>) } : j
      ),
    );
  }
}, []);

useJobEvents({ onEvent: handleJobEvent });
```

---

## 8) Complete Data Flow

### 8.1 Happy path — parallel chapters

```
User submits 3-chapter job
│
│ POST /jobs → 201
│ ┌─ INSERT translation_jobs (pending)
│ ├─ INSERT chapter_translations x3 (pending)
│ ├─ publish → translation.job queue
│ └─ publish event → job.created
│
│ WS /ws?token=...  ← browser connects
│
│   [Job coordinator worker picks up translation.job]
│   ├─ UPDATE job = running
│   ├─ publish chapter-1 msg → translation.chapters
│   ├─ publish chapter-2 msg → translation.chapters
│   ├─ publish chapter-3 msg → translation.chapters
│   └─ publish event → job.status_changed (running, 0/3)
│ ◄── WS: running 0/3
│
│   worker-A picks up chapter-1    worker-B picks up chapter-2    worker-C picks up chapter-3
│   │ GET chapter body             │ GET chapter body             │ GET chapter body
│   │ POST /invoke                 │ POST /invoke                 │ POST /invoke
│   │ [wait 30s-1h, stream]        │ [wait 30s-1h, stream]        │ [wait 30s-1h, stream]
│   │ UPDATE chapter=done          │ UPDATE chapter=done (faster) │ UPDATE chapter=done
│   │ completed_chapters++         │ completed_chapters++         │ completed_chapters++
│   │ check: 1/3 done → not final  │ check: 2/3 done → not final  │ check: 3/3 done → FINAL
│   │ emit chapter_done (1)        │ emit chapter_done (2)        │ UPDATE job=completed
│ ◄── WS ch 1/3                    │                              │ emit job.status_changed (completed)
│                                 │                              │ ack
│ ◄── WS ch 2/3 ──────────────────┘                           ◄── WS: completed 3/3
│ ◄── WS: done ────────────────────────────────────────────────────────────────┘
```

Total time = time of the **slowest chapter**, not the sum of all chapters.

### 8.2 Long AI call (1 hour) — what keeps it alive

```
chapter-worker-A
  │
  │ async with client.stream("POST", "/invoke", ...) as resp:
  │   async for chunk in resp.aiter_bytes():
  │     raw_chunks.append(chunk)   ← await yields to event loop each chunk
  │                                 ← event loop sends AMQP heartbeats
  │                                 ← message stays "unacknowledged" in RabbitMQ (correct)
  │                                 ← RabbitMQ does NOT redeliver (connection is alive)
  │ [1 hour later — final chunk arrives]
  │ write translated_body to DB
  │ ack message
```

### 8.3 Worker crash during AI call

```
chapter-worker-A crashes mid-stream (OOM, SIGKILL, network failure)
│
│ AMQP connection closes abruptly
│
│ RabbitMQ: consumer gone → message returns to translation.chapters queue
│                           (NOT to DLQ — this is a connection-level nack)
│
│ chapter-worker-B picks up the same chapter message
│ starts the AI call from the beginning
│
│ DB state: chapter_translations.status = 'running' (set by A before crash)
│   → chapter-worker-B overrides with its own run (idempotent UPDATE)
```

### 8.4 Scale-out: 5 chapter workers processing simultaneously

```
translation.chapters queue:
  [ch-1] → worker-1   [working, 45 min left]
  [ch-2] → worker-2   [working, 12 min left]
  [ch-3] → worker-3   [working, 58 min left]
  [ch-4] → worker-4   [working, 3 min left]
  [ch-5] → worker-5   [working, 27 min left]
  [ch-6]   (queued — waiting for first worker to finish)
  [ch-7]   (queued)
```

`prefetch_count=1` per worker ensures fair dispatch. No worker takes a second message until it finishes the first.

---

## 9) Files to Modify

| File | Change |
|------|--------|
| `services/translation-service/app/config.py` | Add `rabbitmq_url` |
| `services/translation-service/app/main.py` | Lifespan: `connect_broker()` / `close_broker()` |
| `services/translation-service/app/routers/jobs.py` | Replace `BackgroundTasks` with `publish()` + `publish_event()` |
| `services/translation-service/requirements.txt` | Add `aio_pika>=9.4` |
| `services/api-gateway-bff/src/main.ts` | Add `WsAdapter` |
| `services/api-gateway-bff/src/app.module.ts` | Import `WsModule` |
| `services/api-gateway-bff/package.json` | Add WS + AMQP deps |
| `infra/docker-compose.yml` | Add `rabbitmq`, `translation-worker`, env vars, new volume |
| `frontend/src/pages/BookTranslationPage.tsx` | Fix B1, page-level `useJobEvents` |
| `frontend/src/components/translation/TranslateButton.tsx` | Remove `setInterval`, use `useJobEvents` |

## 10) Files to Create

| File | Purpose |
|------|---------|
| `services/translation-service/app/broker.py` | AMQP connect, `publish()`, `publish_event()` |
| `services/translation-service/app/workers/coordinator.py` | Job fan-out: 1 job msg → N chapter msgs |
| `services/translation-service/app/workers/chapter_worker.py` | Long AI call handler, B2+B3 fix, job completion check |
| `services/translation-service/app/workers/content_extractor.py` | `extract_content()` — B2 fix |
| `services/translation-service/worker.py` | Entry point: consume both queues |
| `services/translation-service/Dockerfile.worker` | Worker container |
| `services/api-gateway-bff/src/ws/amqp.service.ts` | AMQP connection, per-userId subscription |
| `services/api-gateway-bff/src/ws/events.gateway.ts` | NestJS WS gateway |
| `services/api-gateway-bff/src/ws/ws.module.ts` | NestJS module |
| `frontend/src/hooks/useJobEvents.ts` | Browser WS hook: connect, reconnect, route events |

## 11) Implementation Sequence

1. `infra/docker-compose.yml` — add RabbitMQ, verify management UI at `:15672`
2. `app/broker.py` — connect, declare topology, `publish`, `publish_event`
3. `app/workers/content_extractor.py` — B2 fix
4. `app/workers/coordinator.py` — fan-out logic
5. `app/workers/chapter_worker.py` — full chapter processing, B3 fix, `read=None` timeout
6. `worker.py` + `Dockerfile.worker` — entry point, two consumers
7. `translation-service`: update `config.py`, `main.py`, `routers/jobs.py`
8. **Backend smoke test** — `docker compose up --scale translation-worker=2`, submit job via curl, watch RabbitMQ management UI queues drain
9. `amqp.service.ts` + `events.gateway.ts` + `ws.module.ts` — gateway WS module
10. Gateway: wire `app.module.ts`, `main.ts`, `package.json`, env vars
11. `useJobEvents.ts` — frontend hook
12. `TranslateButton.tsx` — remove polling
13. `BookTranslationPage.tsx` — fix B1, page-level subscription
14. **Full E2E test** — submit job in UI, watch WS events arrive, confirm completion

## 12) Scalability Reference

| Concern | Mechanism |
|---------|-----------|
| Many simultaneous jobs | Scale workers: `--scale translation-worker=N` |
| One 1-hour chapter should not block other chapters | Per-chapter queue messages; each worker processes one chapter |
| Parallel chapters within a job | Coordinator fans out N messages; N workers process them simultaneously |
| Long AI call keeps TCP alive | HTTP streaming (`aiter_bytes`) — data flows continuously |
| Long AI call blocks event loop | `await` in async code — event loop free to send AMQP heartbeats |
| JWT expiry during long AI call | Token minted with 4h TTL per chapter — no mid-stream refresh needed |
| Worker crash mid-AI-call | AMQP connection drop → RabbitMQ requeues message → another worker retries |
| Transient errors (DB blip, 503) | Republish with `x-retry-count` header; cap at 5 retries → DLQ |
| Permanent errors (404, logic crash) | `nack(requeue=False)` → DLQ for inspection |
| Double `failed_chapters` increment | `_fail_chapter` uses `WHERE status != 'failed' RETURNING` — idempotent |
| Duplicate finalization of job | Atomic `UPDATE ... WHERE status='running' AND completed+failed=total` — only one worker wins |
| RabbitMQ restart | `connect_robust()` auto-reconnects; persistent messages survive |
| Multiple gateway instances | Each has exclusive queue; fan-out delivers to all; each forwards to its own sockets |
| Managed RabbitMQ `consumer_timeout` | Verify setting is disabled or > max AI call duration before deploying to managed hosts |
| Stuck-pending jobs after crash | Startup recovery sweep marks stale pending jobs failed; consider recovery cron for production |

## 13) Not In Scope

- Transactional outbox (atomic DB write + AMQP publish) — mitigated by startup recovery + future cron
- Notification bell / notification center UI
- Browser push notifications (user not on page)
- WebSocket for collaborative editing
- OAuth token refresh for long WS sessions
- Per-chapter incremental text streaming to browser (emit partial tokens as they arrive)
- True retry-with-backoff (exponential delay between retries) — current fix caps retries at 5 and republishes immediately; backoff via dead-letter + TTL is a future improvement

---

## 14) Architecture Review Findings and Resolutions (v3.0 → v3.1)

Review conducted against v3.0 plan. Four red issues, two yellow.

### 🔴 R1 — Idempotent `_fail_chapter` (double counter increment risk)

**Problem:** If an exception is raised after `_fail_chapter` is already called for a known-bad status (e.g. 404), the outer `except` block would call `_fail_chapter` again, incrementing `failed_chapters` twice for the same chapter.

**Fix:** `_fail_chapter` now uses `WHERE status != 'failed' RETURNING chapter_id`. The counter is only incremented if `RETURNING` is non-null (i.e. this was the first failure write for this chapter). Subsequent calls are no-ops.

```sql
UPDATE chapter_translations
SET status='failed', error_message=$1, finished_at=now()
WHERE job_id=$2 AND chapter_id=$3 AND status != 'failed'
RETURNING chapter_id
-- only increment failed_chapters if RETURNING is non-null
```

### 🔴 R2 — JWT expiry during long AI stream

**Problem:** Token minted at chapter start with 1h TTL. Refresh logic only runs *before* the `/invoke` request. Once streaming begins, no refresh is possible. A 61-minute AI call would use a stale token mid-stream.

**Fix:** Token now minted with `ttl_seconds=14_400` (4 hours) at the start of each chapter. No mid-stream refresh logic needed. The 4h window covers all expected AI call durations with margin. The pre-call refresh check is removed entirely (was also wrong — it ran before the HTTP request was sent, not during streaming).

### 🔴 R3 — Duplicate AMQP connection in `worker.py`

**Problem:** `worker.py` called `connect_broker()` (opens connection #1 via the broker module), then immediately called `aio_pika.connect_robust()` again (opens connection #2). Two connections for no reason.

**Fix:** `broker.py` now exposes `get_channel()` which returns the shared channel opened by `connect_broker()`. `worker.py` calls `get_channel()` instead of opening its own connection.

### 🔴 R4 — All chapter exceptions go to DLQ (no transient/permanent distinction)

**Problem:** `async with message.process(requeue=False)` — any exception (including transient: DB down, book-service 503, network blip) sends the chapter straight to DLQ with no retry.

**Fix:** Two exception classes added: `TransientJobError` and `PermanentJobError`. The `is_transient_error()` classifier also detects `asyncpg.PostgresConnectionError` and `httpx.NetworkError`. Worker dispatch in `worker.py` now calls:
- `nack(requeue=True)` for transient errors — message stays in queue
- `nack(requeue=False)` for permanent errors — message goes to DLQ

Book-service 5xx and provider-registry 5xx are now raised as `TransientJobError`. Book-service 404 and billing 402 remain handled explicitly as permanent failures (mark chapter failed, return normally → ack).

### 🟡 Y1 — TOCTOU in `_check_job_completion` (atomic SQL fix)

**Problem:** Original design did a `SELECT` to read counters, computed `final_status` in Python, then issued a separate `UPDATE WHERE status='running'`. Between SELECT and UPDATE, another worker could write stale data into `final_status`.

**Fix:** The entire check-and-write is now a single atomic SQL statement:

```sql
UPDATE translation_jobs SET
  status = CASE
    WHEN failed_chapters = 0     THEN 'completed'
    WHEN completed_chapters > 0  THEN 'partial'
    ELSE                              'failed'
  END,
  finished_at = now()
WHERE job_id = $1
  AND status  = 'running'
  AND (completed_chapters + failed_chapters) = total_chapters
RETURNING status, completed_chapters, failed_chapters
```

No Python-side status computation. Counters read and decision made inside one DB statement. Only the worker whose UPDATE matches emits the final event.

### 🟡 Y2 — Managed RabbitMQ `consumer_timeout` and stuck-pending recovery

**Noted, not blocked:** If deploying to a managed RabbitMQ provider (CloudAMQP etc.), verify `consumer_timeout` is disabled or set above the maximum expected AI call duration (recommend > 2h). On self-hosted RabbitMQ 3.x it is disabled by default.

For stuck-pending jobs: the existing startup recovery sweep (marks jobs older than 1h as failed) handles crash recovery on restart. A production cron job that republishes orphaned pending jobs (created > 5 min ago, no corresponding in-flight AMQP message) is recommended but deferred to a future operations plan.

---

## 15) Architecture Review Findings and Resolutions (v3.1 → v3.2)

Review conducted against v3.1 plan. Four yellow issues from the v3.1 review are now resolved.

### ✅ Y1 (v3.1) — Coordinator fan-out idempotency

**Problem:** `on_job` uses `message.process(requeue=True)`. If the coordinator crashes mid-publish (e.g. published 5 of 10 chapter messages then died), on retry it publishes all 10 again. The first 5 chapters get 2 messages each → two workers race on the same chapter, wasting 5 redundant AI calls.

**Fix:** `handle_job_message` now reads the job's current `status` before doing anything. If status is already `'running'`, the job was already fanned out — return immediately (caller acks). Fan-out only proceeds from `pending`.

```sql
SELECT status FROM translation_jobs WHERE job_id=$1
-- If 'running': return (ack, no duplicate publish)
-- If 'pending': proceed with UPDATE + fan-out
```

### ✅ Y2 (v3.1) — Unbounded transient requeue

**Problem:** `nack(requeue=True)` returns the message to the front of the queue with immediate redelivery. If a transient error persists (book-service down 30 min), all worker capacity is consumed by a tight retry loop with no backoff and no limit.

**Fix:** `on_chapter` in `worker.py` now reads `x-retry-count` from message headers. After 5 transient retries the message is nacked to the DLQ. On retry, the original message is acked and a new message with `x-retry-count + 1` is published (raw `nack(requeue=True)` would reset the header).

### ✅ Y3 (v3.1) — NestJS AMQP no auto-reconnect

**Problem:** `amqplib`'s plain `connect()` does not auto-reconnect. A RabbitMQ restart silently kills the gateway's AMQP connection — no WebSocket client receives any further events.

**Fix:** `AmqpService` now uses a `connectWithRetry()` loop (3-second backoff). The `close` event on the connection triggers `onModuleInit()` re-initialization. `error` event is swallowed (no unhandled rejection; `close` always follows). `destroyed` flag prevents reconnect loops during graceful shutdown.

### ✅ Y4 (v3.1) — WS reconnect state gap

**Problem:** If `accessToken` rotates, `useEffect` re-runs, closes the old socket, and opens a new one. Events fired during the 3-second reconnect window are lost. A missed `job.status_changed` leaves the UI stale until the next event or page refresh.

**Fix:** `useJobEvents` now accepts an optional `onReconnect` callback, invoked from `ws.onopen` after every successful connect. `TranslateButton` passes `handleReconnect` which calls `GET /jobs/:id` and patches local state with the latest DB truth, filling any gap from the reconnect window.
