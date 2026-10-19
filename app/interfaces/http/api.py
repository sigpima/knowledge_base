from contextlib import asynccontextmanager
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException

from app.core.services.knowledge_service import KnowledgeService
from app.domains.quotation.exception import EntityNotFoundError
from app.infrastructure.database.postgres.session import init_db
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
