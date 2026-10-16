"""Pydantic data models and schemas for Company Brain."""

from datetime import datetime, timezone
from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator


# --- Document & Ingestion Models ---

class DocumentFrontmatter(BaseModel):
    """Schema for validating Markdown frontmatter metadata."""
    id: str = Field(..., description="Unique document identifier, e.g. NEX-OVR-001")
    title: str = Field(..., description="Human-readable document title")
    category: str = Field(..., description="Functional category, e.g. HR, Engineering")
    author: str = Field(..., description="Fictional document author")
    last_updated: str = Field(..., description="ISO 8601 formatted update timestamp")
    version: str = Field(..., description="Document semantic version")
    access_classification: str = Field(
        ...,
        description="Target access clearance: employee, manager, hr, finance, executive, admin"
    )

    @field_validator("version", mode="before")
    @classmethod
    def serialize_version(cls, v: Any) -> str:
        return str(v)

    @field_validator("last_updated", mode="before")
    @classmethod
    def serialize_last_updated(cls, v: Any) -> str:
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


class DocumentSummary(BaseModel):
    """Lightweight document representation for listing and navigation."""
    id: str
    title: str
    category: str
    author: str
    last_updated: str
    version: str
    access_classification: str
    chunk_count: int = 0


class DocumentDetail(BaseModel):
    """Full document representation including markdown content and provenance."""
    id: str
    title: str
    category: str
    author: str
    last_updated: str
    version: str
    access_classification: str
    file_path: str
    file_hash: str
    raw_content: str
    chunk_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DocumentChunk(BaseModel):
    """Individual chunk representation used in retrieval indexing."""
    id: str
    document_id: str
    chunk_index: int
    heading: Optional[str] = None
    content: str


# --- Search & Retrieval Models ---

class SearchRequest(BaseModel):
    """Payload for knowledge search query."""
    query: str = Field(..., min_length=1, description="Keyword search query or question")
    limit: int = Field(5, ge=1, le=20, description="Maximum number of search excerpts to return")


class SearchResultItem(BaseModel):
    """Individual retrieved search excerpt with relevance score and metadata."""
    document_id: str
    title: str
    category: str
    access_classification: str
    heading: Optional[str] = None
    excerpt: str
    score: float


class SearchResponse(BaseModel):
    """Complete search query response."""
    query: str
    total_results: int
    results: List[SearchResultItem]
    role_applied: str


# --- Question Answering Models ---

class AskRequest(BaseModel):
    """Payload for grounded AI answer generation."""
    question: str = Field(..., min_length=2, description="Employee question to answer")
    max_sources: int = Field(4, ge=1, le=10, description="Max grounding excerpts to feed to the model")



class SourceCitation(BaseModel):
    """Reference citation linking the answer to verified internal sources."""
    document_id: str
    title: str
    category: str
    access_classification: str
    heading: Optional[str] = None
    excerpt: str


class AskResponse(BaseModel):
    """Grounded AI answer with source citations and confidence classification."""
    question: str
    answer: str
    sources: List[SourceCitation]
    provider: str = Field(..., description="Active answer provider: e.g. gemini, retrieval_only")
    confidence: str = Field(..., description="grounded or insufficient_evidence")
    role_applied: str


# --- Synchronization Models ---

class SyncResult(BaseModel):
    """Summary of a knowledge base synchronization run."""
    status: str = Field(..., description="success or partial_failure")
    added: int = 0
    modified: int = 0
    deleted: int = 0
    unchanged: int = 0
    total_documents: int = 0
    errors: List[str] = []
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SyncStatusResponse(BaseModel):
    """Current status of the background synchronization pipeline."""
    is_syncing: bool
    last_sync: Optional[SyncResult] = None


# --- System Health Models ---

class HealthResponse(BaseModel):
    """System health and operational metadata."""
    status: str
    app: str
    version: str
    environment: str
    llm_provider: str
    gemini_configured: bool
    documents_indexed: int
    chunks_indexed: int
