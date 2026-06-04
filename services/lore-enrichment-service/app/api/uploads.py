"""Uploads router — mode F (attach files), Compose slice 3.

`POST /v1/lore-enrichment/uploads` (multipart): accept a `.txt/.md/.pdf/.docx/.epub`
file + the book/project scope + an author license assertion. The raw bytes go to
MinIO; the row is created ``status='processing'`` and text extraction (+OCR for
scanned PDFs) runs in the BACKGROUND (F10 — a 300-page scan must not time out the
request). ``GET /uploads/{id}`` polls until ``ready``/``failed``.

`/compose` (``input_source='files'``) then loads each ready upload's extracted text
and ingests it as a grounding corpus (mode-C path) — see compose.py.

H0/licensing: ``license_asserted`` is default-deny (copyrighted/unknown → 403 before
anything is stored). Per-user/book scope (Q3); the poll never returns the full text.
"""

from __future__ import annotations

import asyncio
import io
import logging
from uuid import UUID, uuid4

import asyncpg
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)

from app.api.license_assert import resolve_asserted_license
from app.api.principal import Principal, require_principal
from app.config import settings
from app.deps import get_db
from app.files.extract import SUPPORTED_EXTENSIONS, extract_text, file_extension
from app.storage.minio_client import ensure_bucket, upload_file

logger = logging.getLogger("lore_enrichment.uploads")

router = APIRouter(prefix="/v1/lore-enrichment/uploads", tags=["uploads"])


def _view(row: asyncpg.Record) -> dict:
    """Public poll shape — never includes the full extracted_text."""
    return {
        "upload_id": str(row["upload_id"]),
        "filename": row["filename"],
        "mime": row["mime"],
        "pages": row["pages"],
        "extracted_chars": row["extracted_chars"],
        "ocr_used": row["ocr_used"],
        "license_asserted": row["license_asserted"],
        "status": row["status"],
        "error": row["error_message"],
    }


async def fetch_upload(pool: asyncpg.Pool, user_id, upload_id: UUID) -> asyncpg.Record | None:
    """Load one upload scoped to the owner (compose + the poll both use this)."""
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM enrichment_upload WHERE upload_id=$1 AND user_id=$2",
            upload_id, user_id,
        )


async def _extract_and_store(pool: asyncpg.Pool, upload_id: UUID, filename: str, data: bytes) -> None:
    """Background: extract text (+OCR) off the event loop, then flip status. A
    failure is recorded as status='failed' + error_message (never crashes the loop)."""
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None, lambda: extract_text(filename, data, max_pages=settings.upload_max_pages)
        )
        async with pool.acquire() as conn:
            await conn.execute(
                """UPDATE enrichment_upload
                   SET status='ready', extracted_text=$2, extracted_chars=$3,
                       pages=$4, ocr_used=$5, updated_at=now()
                   WHERE upload_id=$1""",
                upload_id, result.text, len(result.text), result.pages, result.ocr_used,
            )
        logger.info("upload %s extracted (chars=%d pages=%d ocr=%s)",
                    upload_id, len(result.text), result.pages, result.ocr_used)
    except Exception as exc:  # noqa: BLE001 — record the failure for the poll, don't crash
        logger.warning("upload %s extraction failed", upload_id, exc_info=True)
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE enrichment_upload SET status='failed', error_message=$2, updated_at=now() WHERE upload_id=$1",
                upload_id, str(exc)[:500],
            )


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_upload(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    book_id: UUID = Form(...),
    project_id: UUID = Form(...),
    license_asserted: str = Form(...),
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Accept a file → store raw in MinIO → create the row → extract in background."""
    if principal.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required")
    ext = file_extension(file.filename or "")
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"unsupported file type {ext!r} (allowed: {sorted(SUPPORTED_EXTENSIONS)})",
        )
    store_license = resolve_asserted_license(license_asserted)
    if store_license is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=("license_asserted must be one of public_domain | licensed | owned — "
                    "copyrighted material cannot be ingested"),
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty file")
    if len(data) > settings.upload_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"file too large ({len(data)} bytes > {settings.upload_max_bytes} cap)",
        )

    # NOTE (accepted, D-COMPOSE-S3-UPLOAD-REAPER): MinIO write precedes the row
    # INSERT, so an INSERT failure orphans the object; a service restart mid-extract
    # strands a row in 'processing' (→ the files branch 409s on it forever). No data
    # corruption; a reaper (sweep stale 'processing' + orphan objects) is a follow-up.
    upload_id = uuid4()
    key = f"{principal.user_id}/{book_id}/{upload_id}{ext}"
    try:
        await ensure_bucket()
        await upload_file(key, io.BytesIO(data), content_type=file.content_type or "application/octet-stream")
    except Exception as exc:  # noqa: BLE001 — storage down → clear 502, nothing persisted
        logger.warning("MinIO upload failed", exc_info=True)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"object storage failed: {exc}")

    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO enrichment_upload
               (upload_id, user_id, book_id, project_id, filename, mime, size_bytes,
                license_asserted, storage_key, status)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'processing')""",
            upload_id, principal.user_id, book_id, project_id, file.filename or "",
            file.content_type or "", len(data), store_license, key,
        )

    background.add_task(_extract_and_store, pool, upload_id, file.filename or "", data)
    return {"upload_id": str(upload_id), "filename": file.filename, "status": "processing"}


@router.get("/{upload_id}")
async def get_upload(
    upload_id: UUID,
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Poll an upload's extraction status (owner-scoped; never returns the text)."""
    if principal.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required")
    row = await fetch_upload(pool, principal.user_id, upload_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="upload not found")
    return _view(row)
