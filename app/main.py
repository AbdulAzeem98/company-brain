
"""FastAPI application entrypoint for Company Brain knowledge platform."""

import logging
from contextlib import asynccontextmanager
from typing import List

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.models import (
    AskRequest,
    AskResponse,
    DocumentDetail,
    DocumentSummary,
    HealthResponse,
    SearchRequest,
    SearchResponse,
    SyncResult,
    SyncStatusResponse,
)
from app.permissions import get_current_role
from app.services import get_knowledge_service, get_sync_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("company_brain")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database and perform initial ingestion when necessary."""
    settings = get_settings()
    logger.info(
        "Starting %s v%s...",
        settings.APP_NAME,
        settings.APP_VERSION,
    )

    init_db(settings.DATABASE_PATH)

    knowledge_service = get_knowledge_service()
    doc_count, _ = knowledge_service.get_indexed_counts()

    if doc_count == 0:
        logger.info(
            "Knowledge index is empty. Triggering initial ingestion."
        )
        sync_service = get_sync_service()
        try:
            await sync_service.trigger_sync()
        except Exception:
            logger.exception("Initial knowledge synchronization failed.")

    yield

    logger.info("Shutting down Company Brain API.")


app = FastAPI(
    title="Company Brain — AI Harness & Knowledge Platform",
    description=(
        "Enterprise knowledge retrieval and grounded AI answer generation "
        "for Nexora Technologies (Synthetic Data Demo). Supports role-based "
        "access control, SQLite FTS5 search, Gemini answering, and MCP."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# Configure trusted browser origins through the CORS_ORIGINS environment
# variable. Local Streamlit development does not normally require browser CORS.
settings = get_settings()
cors_origins = [
    origin.strip().rstrip("/")
    for origin in getattr(settings, "CORS_ORIGINS", ["http://localhost:8501"])
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Return application health and indexing statistics."""
    settings = get_settings()
    knowledge_service = get_knowledge_service()
    doc_count, chunk_count = knowledge_service.get_indexed_counts()

    return HealthResponse(
        status="ok",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
        llm_provider=knowledge_service.llm.name,
        gemini_configured=bool(settings.GEMINI_API_KEY),
        documents_indexed=doc_count,
        chunks_indexed=chunk_count,
    )


@app.get(
    "/documents",
    response_model=List[DocumentSummary],
    tags=["Documents"],
)
async def list_documents(
    current_role: str = Depends(get_current_role),
):
    """List documents permitted for the resolved role."""
    knowledge_service = get_knowledge_service()
    return knowledge_service.list_documents(role=current_role)


@app.get(
    "/documents/{document_id}",
    response_model=DocumentDetail,
    tags=["Documents"],
)
async def get_document(
    document_id: str,
    current_role: str = Depends(get_current_role),
):
    """Retrieve a document subject to server-side RBAC."""
    knowledge_service = get_knowledge_service()
    return knowledge_service.get_document(
        document_id=document_id,
        role=current_role,
    )


@app.post("/search", response_model=SearchResponse, tags=["Retrieval"])
async def search_knowledge(
    payload: SearchRequest,
    current_role: str = Depends(get_current_role),
):
    """Search the knowledge base with role-based filtering."""
    knowledge_service = get_knowledge_service()
    return knowledge_service.search(
        query=payload.query,
        role=current_role,
        limit=payload.limit,
    )


@app.post("/ask", response_model=AskResponse, tags=["AI Q&A"])
async def ask_question(
    payload: AskRequest,
    current_role: str = Depends(get_current_role),
):
    """Answer a question using authorized evidence and source citations."""
    knowledge_service = get_knowledge_service()
    return await knowledge_service.ask(
        question=payload.question,
        role=current_role,
        max_sources=payload.max_sources,
    )


@app.post("/sync", response_model=SyncResult, tags=["Knowledge Sync"])
async def sync_knowledge(
    current_role: str = Depends(get_current_role),
):
    """Allow administrators to trigger a knowledge synchronization."""
    if current_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: administrator role required.",
        )

    return await get_sync_service().trigger_sync()


@app.get(
    "/sync/status",
    response_model=SyncStatusResponse,
    tags=["Knowledge Sync"],
)
async def get_sync_status(
    current_role: str = Depends(get_current_role),
):
    """Allow administrators to view synchronization status."""
    if current_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: administrator role required.",
        )

    return get_sync_service().get_status()
