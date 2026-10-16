
"""Knowledge orchestration service uniting RBAC, FTS5 retrieval, and answer providers."""

import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import HTTPException, status

from app.config import get_settings
from app.database import get_db_connection
from app.llm import get_llm_provider
from app.llm.base import BaseLLMProvider
from app.models import (
    AskResponse,
    DocumentDetail,
    DocumentSummary,
    SearchResponse,
    SearchResultItem,
    SourceCitation,
)
from app.permissions import (
    get_allowed_classifications_for_role,
    normalize_role,
)
from app.retrieval import BaseRetrievalEngine, SQLiteFTS5RetrievalEngine

logger = logging.getLogger(__name__)


class KnowledgeService:
    """Core knowledge service enforcing RBAC for retrieval and synthesis."""

    def __init__(
        self,
        retrieval_engine: Optional[BaseRetrievalEngine] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
        db_path: Optional[Path] = None,
    ):
        settings = get_settings()
        self.retrieval = retrieval_engine or SQLiteFTS5RetrievalEngine()
        self.llm = llm_provider or get_llm_provider()
        self.db_path = db_path or getattr(
            self.retrieval, "db_path", settings.DATABASE_PATH
        )

    @staticmethod
    def _document_to_section_items(
        document: DocumentDetail,
    ) -> List[SearchResultItem]:
        """Split an authorized document's full Markdown into heading sections."""
        content = document.raw_content or ""
        if not content.strip():
            return []

        # Match Markdown headings while preserving the original section content.
        heading_matches = list(
            re.finditer(r"(?m)^#{1,6}\s+(.+?)\s*$", content)
        )

        if not heading_matches:
            return [
                SearchResultItem(
                    document_id=document.id,
                    title=document.title,
                    category=document.category,
                    access_classification=document.access_classification,
                    heading=document.title,
                    excerpt=content.strip(),
                    score=1000.0,
                )
            ]

        section_items: List[SearchResultItem] = []

        for index, match in enumerate(heading_matches):
            heading = match.group(1).strip()
            section_start = match.end()
            section_end = (
                heading_matches[index + 1].start()
                if index + 1 < len(heading_matches)
                else len(content)
            )
            section_content = content[section_start:section_end].strip()

            if not section_content:
                continue

            section_items.append(
                SearchResultItem(
                    document_id=document.id,
                    title=document.title,
                    category=document.category,
                    access_classification=document.access_classification,
                    heading=heading,
                    excerpt=section_content,
                    score=1000.0 - index * 0.01,
                )
            )

        return section_items

    def search(
        self,
        query: str,
        role: Optional[str] = None,
        limit: int = 5,
    ) -> SearchResponse:
        """Search company knowledge with server-side RBAC filtering."""
        user_role = normalize_role(role)
        allowed = get_allowed_classifications_for_role(user_role)

        items = self.retrieval.search(
            query=query,
            allowed_classifications=allowed,
            limit=limit,
        )

        return SearchResponse(
            query=query,
            total_results=len(items),
            results=items,
            role_applied=user_role.value,
        )

    async def ask(
        self,
        question: str,
        role: Optional[str] = None,
        max_sources: int = 4,
    ) -> AskResponse:
        """Retrieve authorized evidence and answer using only that evidence."""
        user_role = normalize_role(role)
        allowed = get_allowed_classifications_for_role(user_role)

        # If a document ID is explicitly named, restrict the answer to that ID.
        requested_doc_ids = {
            match.upper()
            for match in re.findall(
                r"\bNEX-[A-Z]+-\d{3}\b",
                question,
                flags=re.IGNORECASE,
            )
        }

        question_lower = question.lower()
        asks_milestones = any(
            term in question_lower
            for term in (
                "30-60-90",
                "30-day",
                "60-day",
                "90-day",
                "30 day",
                "60 day",
                "90 day",
                "31–60",
                "61–90",
                "success criteria",
                "first 30 days",
                "first 90 days",
            )
        )

        queries = [question]
        if asks_milestones:
            queries.extend(
                [
                    "30-Day Milestone Context Integration onboarding",
                    "60-Day Milestone Autonomy Contribution onboarding",
                    "90-Day Milestone Full Ownership onboarding",
                ]
            )

        candidate_limit = min(max(max_sources * 3, 10), 20)
        merged: dict[tuple[str, str, str], SearchResultItem] = {}

        # Every search applies the same server-side classification filter.
        for search_query in queries:
            try:
                results = self.retrieval.search(
                    query=search_query,
                    allowed_classifications=allowed,
                    limit=candidate_limit,
                )
            except Exception:
                logger.exception("Knowledge retrieval failed")
                continue

            for item in results:
                if (
                    requested_doc_ids
                    and item.document_id.upper() not in requested_doc_ids
                ):
                    continue

                key = (
                    item.document_id,
                    item.heading or "",
                    item.excerpt,
                )
                current = merged.get(key)
                if current is None or item.score > current.score:
                    merged[key] = item

        # For explicit milestone questions, use the full document only after
        # the retrieval engine has verified the caller's allowed classifications.
        if asks_milestones and requested_doc_ids:
            for document_id in sorted(requested_doc_ids):
                try:
                    document, is_forbidden = self.retrieval.get_document(
                        document_id,
                        allowed,
                    )
                except Exception:
                    logger.exception(
                        "Authorized full-document retrieval failed for %s",
                        document_id,
                    )
                    continue

                # Never use a document returned as forbidden.
                if is_forbidden or document is None:
                    continue

                for item in self._document_to_section_items(document):
                    key = (
                        item.document_id,
                        item.heading or "",
                        item.excerpt,
                    )
                    current = merged.get(key)

                    # Prefer the full section over a shortened search snippet.
                    if current is None or item.score > current.score:
                        merged[key] = item

        retrieved_items = sorted(
            merged.values(),
            key=lambda item: item.score,
            reverse=True,
        )

        if asks_milestones:
            milestone_markers = (
                "30-day milestone",
                "60-day milestone",
                "90-day milestone",
            )
            selected: List[SearchResultItem] = []
            seen_sections: set[tuple[str, str]] = set()

            # Select the best available full section for each milestone.
            for marker in milestone_markers:
                match = next(
                    (
                        item
                        for item in retrieved_items
                        if marker in (item.heading or "").lower()
                    ),
                    None,
                )
                if match is not None:
                    key = (
                        match.document_id,
                        (match.heading or "").lower(),
                    )
                    if key not in seen_sections:
                        selected.append(match)
                        seen_sections.add(key)

            # Add distinct supporting sections, including Week 1.
            for item in retrieved_items:
                if len(selected) >= candidate_limit:
                    break

                key = (
                    item.document_id,
                    (item.heading or "").lower(),
                )
                if key not in seen_sections:
                    selected.append(item)
                    seen_sections.add(key)

            retrieved_items = selected
        else:
            retrieved_items = retrieved_items[:candidate_limit]

        answer_text, confidence = await self.llm.generate_answer(
            question,
            retrieved_items,
        )

        # Cite each distinct document section supplied to the answer provider.
        citations: List[SourceCitation] = []
        seen_citations: set[tuple[str, str]] = set()

        for item in retrieved_items:
            key = (item.document_id, item.heading or "")
            if key in seen_citations:
                continue
            seen_citations.add(key)

            citations.append(
                SourceCitation(
                    document_id=item.document_id,
                    title=item.title,
                    category=item.category,
                    access_classification=item.access_classification,
                    heading=item.heading,
                    excerpt=item.excerpt,
                )
            )

        return AskResponse(
            question=question,
            answer=answer_text,
            sources=citations,
            provider=self.llm.name,
            confidence=confidence,
            role_applied=user_role.value,
        )

    def get_document(
        self,
        document_id: str,
        role: Optional[str] = None,
    ) -> DocumentDetail:
        """Return a document only after authorization is verified."""
        user_role = normalize_role(role)
        allowed = get_allowed_classifications_for_role(user_role)

        doc, is_forbidden = self.retrieval.get_document(
            document_id,
            allowed,
        )

        if is_forbidden:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access denied. Document '{document_id}' requires higher "
                    f"clearance. Current role '{user_role.value}' is not "
                    "authorized to view it."
                ),
            )

        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Document '{document_id}' not found in the knowledge "
                    "repository."
                ),
            )

        return doc

    def list_documents(
        self,
        role: Optional[str] = None,
    ) -> List[DocumentSummary]:
        """List documents filtered by role clearance."""
        user_role = normalize_role(role)
        allowed = get_allowed_classifications_for_role(user_role)
        return self.retrieval.list_documents(allowed)

    def get_indexed_counts(self) -> Tuple[int, int]:
        """Return total indexed documents and chunks."""
        with get_db_connection(self.db_path) as conn:
            doc_count = conn.execute(
                "SELECT COUNT(*) AS count FROM documents"
            ).fetchone()["count"]
            chunk_count = conn.execute(
                "SELECT COUNT(*) AS count FROM document_chunks"
            ).fetchone()["count"]

        return doc_count, chunk_count


_knowledge_service_instance: Optional[KnowledgeService] = None


def get_knowledge_service() -> KnowledgeService:
    """Return the process-wide knowledge service instance."""
    global _knowledge_service_instance
    if _knowledge_service_instance is None:
        _knowledge_service_instance = KnowledgeService()
    return _knowledge_service_instance
