"""
Mock Audio Service — implements OpenAI-compatible TTS/STT endpoints for testing.

This is NOT a real TTS/STT service. It returns:
- TTS: a short sine-wave WAV file (440Hz, 1 second)
- STT: a hardcoded mock transcription
- Voices: 2 dummy voices
- Models: 2 dummy model entries

Usage:
  pip install -r requirements.txt
  uvicorn main:app --port 8600

Or via Docker Compose:
  AUDIO_SERVICE_URL=http://mock-audio-service:8600 docker compose up
"""

import io
import math
import struct
import logging
from typing import Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

app = FastAPI(title="Mock Audio Service", version="0.1.0")
log = logging.getLogger("mock-audio")

MOCK_API_KEY = "mock-audio-key"


def check_auth(authorization: Optional[str]):
    """Validate Bearer token (accepts any non-empty token for testing)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")


# ── TTS ─────────────────────────────────────────────────────────────────


class TTSRequest(BaseModel):
    model: str = "mock-tts-v1"
    voice: str = "alloy"
    input: str = ""
    response_format: str = "mp3"
    speed: float = 1.0
    instructions: Optional[str] = None


def generate_wav(text: str, duration_s: float = 1.0, sample_rate: int = 24000) -> bytes:
    """Generate a simple sine-wave WAV file (440Hz tone)."""
    n_samples = int(sample_rate * duration_s)
    freq = 440.0
    samples = []
    for i in range(n_samples):
        t = i / sample_rate
        sample = int(16000 * math.sin(2 * math.pi * freq * t))
        samples.append(struct.pack("<h", max(-32768, min(32767, sample))))

    audio_data = b"".join(samples)
    data_size = len(audio_data)

    # WAV header (44 bytes)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,        # chunk size
        1,         # PCM
        1,         # mono
        sample_rate,
        sample_rate * 2,  # byte rate
        2,         # block align
        16,        # bits per sample
        b"data",
        data_size,
    )
    return header + audio_data


@app.post("/v1/audio/speech")
async def tts_generate(
    req: TTSRequest,
    authorization: Optional[str] = Header(None),
):
    """Mock TTS — returns a sine-wave WAV regardless of input."""
    check_auth(authorization)

    if not req.input:
        raise HTTPException(status_code=400, detail="input is required")
    if len(req.input) > 4096:
        raise HTTPException(status_code=400, detail="input exceeds 4096 character limit")

    # Duration proportional to text length (min 0.5s, max 5s)
    duration = max(0.5, min(5.0, len(req.input) / 100.0))
    wav_bytes = generate_wav(req.input, duration_s=duration)

    log.info("TTS: model=%s voice=%s input_len=%d duration=%.1fs", req.model, req.voice, len(req.input), duration)

    # For streaming test: return chunked
    def chunked():
        chunk_size = 4096
        for i in range(0, len(wav_bytes), chunk_size):
            yield wav_bytes[i : i + chunk_size]

    return StreamingResponse(
        chunked(),
        media_type="audio/wav",
        headers={
            "Transfer-Encoding": "chunked",
            "X-Mock-Duration": f"{duration:.1f}",
            "X-Mock-Characters": str(len(req.input)),
        },
    )


# ── STT ─────────────────────────────────────────────────────────────────


@app.post("/v1/audio/transcriptions")
async def stt_transcribe(
    file: UploadFile = File(...),
    model: str = Form("mock-stt-v1"),
    language: Optional[str] = Form(None),
    response_format: str = Form("json"),
    temperature: float = Form(0),
    prompt: Optional[str] = Form(None),
    authorization: Optional[str] = Header(None),
):
    """Mock STT — returns a fixed transcription regardless of audio input."""
    check_auth(authorization)

    content = await file.read()
    audio_size = len(content)

    log.info("STT: model=%s language=%s file=%s size=%d", model, language, file.filename, audio_size)

    # Estimate "duration" from file size (rough: 16kHz 16-bit mono = 32KB/s)
    estimated_duration = max(0.5, audio_size / 32000.0)

    mock_text = f"Mock transcription of {audio_size} bytes audio"
    if language:
        mock_text += f" (language: {language})"

    if response_format == "text":
        return Response(content=mock_text, media_type="text/plain")

    if response_format == "verbose_json":
        return {
            "text": mock_text,
            "language": language or "en",
            "duration": round(estimated_duration, 2),
            "segments": [
                {
                    "start": 0.0,
                    "end": round(estimated_duration, 2),
                    "text": mock_text,
                }
            ],
        }

    # Default: json
    return {"text": mock_text}


# ── Voices ──────────────────────────────────────────────────────────────


@app.get("/v1/voices")
async def list_voices(authorization: Optional[str] = Header(None)):
    check_auth(authorization)
    return {
        "voices": [
            {"voice_id": "alloy", "name": "Alloy", "language": "en", "gender": "neutral"},
            {"voice_id": "nova", "name": "Nova", "language": "en", "gender": "female"},
            {"voice_id": "echo", "name": "Echo", "language": "en", "gender": "male"},
        ]
    }


# ── Models ──────────────────────────────────────────────────────────────


@app.get("/v1/models")
async def list_models(authorization: Optional[str] = Header(None)):
    check_auth(authorization)
    return {
        "object": "list",
        "data": [
            {
                "id": "mock-tts-v1",
                "object": "model",
                "created": 1700000000,
                "owned_by": "mock-audio-service",
                "capabilities": {"tts": True, "voices": ["alloy", "nova", "echo"]},
            },
            {
                "id": "mock-stt-v1",
                "object": "model",
                "created": 1700000000,
                "owned_by": "mock-audio-service",
                "capabilities": {"stt": True},
            },
        ],
    }


# ── Health ──────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mock-audio-service", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8600)
