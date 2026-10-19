from contextlib import asynccontextmanager
from typing import Dict, Optional

import dataclasses
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.core.services.knowledge_service import KnowledgeService
from app.domains.quotation.application.services.ingest.loader import QuotationFileError, load_quotation_text
from app.domains.quotation.application.services.ingest.writer import DuplicateProjectError, ingest_quotation
from app.domains.quotation.exception import EntityNotFoundError
from app.infrastructure.config.config import settings
from app.infrastructure.database.postgres.session import SessionLocal, init_db
from app.infrastructure.observability.logger import get_logger

logger = get_logger(__name__)


knowledge_service: Optional[KnowledgeService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global knowledge_service
    logger.info("Initializing database")
    init_db()
    knowledge_service = KnowledgeService()
    yield


app = FastAPI(title="Knowledge Base API", lifespan=lifespan)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


def _ingest_text(text: str, source_file: str):
    file = load_quotation_text(text, source_file)
    with SessionLocal() as session:
        return ingest_quotation(session, file, source_file)


async def _read_limited_body(request: Request) -> bytes:
    limit = settings.ingest_max_body_bytes
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status_code=413, detail=f"Body vượt quá {limit} byte")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(status_code=413, detail=f"Body vượt quá {limit} byte")
        chunks.append(chunk)
    return b"".join(chunks)


@app.post("/ingest", status_code=201)
async def ingest(request: Request, source_file: str = "http-upload.yaml"):
    """Nhận một file báo giá YAML trong body, kiểm tra rồi ghi vào DB."""
    body = await _read_limited_body(request)
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return JSONResponse(status_code=422, content={"errors": ["<file>: body phải là UTF-8"]})
    try:
        result = await run_in_threadpool(_ingest_text, text, Path(source_file).name or "http-upload.yaml")
    except QuotationFileError as exc:
        return JSONResponse(status_code=422, content={"errors": exc.errors})
    except DuplicateProjectError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return dataclasses.asdict(result)


@app.get("/work-items/{item_id}")
def get_work_item(item_id: int):
    if knowledge_service is None:
        raise HTTPException(status_code=503, detail="Knowledge service not initialized")

    work_item = knowledge_service.get_work_item(item_id)

    if work_item is None:
        raise HTTPException(
            status_code=404,
            detail=str(EntityNotFoundError(entity_name="WorkItem", entity_id=item_id)),
        )

    return {
        "item_id": work_item.item_id,
        "name": work_item.name,
        "description": work_item.description,
        "quantity": work_item.quantity,
        "unit": work_item.unit,
        "unit_price": work_item.unit_price,
        "currency": work_item.currency,
        "total_price": work_item.total_price,
    }


def run(port: int = 8000) -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=port)
