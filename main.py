"""
markitdown-proxy — Docling-compatible HTTP proxy for document conversion.

Mimics the Docling /v1/convert/file API so Open WebUI can point
DOCLING_SERVER_URL here without any other config changes.

Routing:
  .pdf / images  →  proxied to Docling (layout + OCR)
  .docx .xlsx
  .pptx .html
  .csv .txt .md  →  converted locally with MarkItDown
"""

import logging
import os
import tempfile
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from markitdown import MarkItDown

DOCLING_URL = os.getenv("DOCLING_URL", "http://docling.ai.svc.cluster.local:5001")

DOCLING_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif", ".webp"}

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="markitdown-proxy")
_md = MarkItDown()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    return {"status": "ready"}


@app.post("/v1/convert/file")
async def convert_file(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    content = await file.read()

    if suffix in DOCLING_EXTS:
        log.info("→ Docling  %s (%d bytes)", file.filename, len(content))
        async with httpx.AsyncClient(timeout=300) as client:
            try:
                resp = await client.post(
                    f"{DOCLING_URL}/v1/convert/file",
                    files={"files": (file.filename, content,
                                    file.content_type or "application/octet-stream")},
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                log.error("Docling error: %s", exc)
                raise HTTPException(status_code=502, detail=f"Docling error: {exc}")
        return JSONResponse(resp.json())

    # All other formats → MarkItDown
    log.info("→ MarkItDown  %s (%d bytes)", file.filename, len(content))
    suffix = suffix or ".bin"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        result = _md.convert(tmp_path)
        md_text = result.text_content or ""
    except Exception as exc:
        log.error("MarkItDown error: %s", exc)
        raise HTTPException(status_code=422, detail=f"MarkItDown conversion failed: {exc}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    log.info("   → %d chars markdown", len(md_text))
    return JSONResponse({"document": {"md_content": md_text}})
