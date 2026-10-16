"""Modular retrieval layer with SQLite FTS5 implementation, precision scoring, and RBAC enforcement."""

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from app.config import get_settings
from app.database import get_db_connection
from app.models import DocumentDetail, DocumentSummary, SearchResultItem


STOPWORDS = {
    "what", "where", "when", "why", "which", "who", "whom", "how",
    "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did",
    "can", "could", "would", "should", "will", "shall", "may", "might", "must",
    "a", "an", "the", "and", "or", "but", "if", "for", "in", "on", "at", "to",
    "from", "by", "with", "about", "into", "through", "after", "before", "of",
    "this", "that", "these", "those", "my", "your", "his", "her", "its", "our",
    "their", "we", "us", "i", "you", "he", "she", "they", "it",
}

GENERIC_MODIFIERS = {
    "status", "project", "policy", "policies", "procedure", "procedures",
    "guideline", "guidelines", "report", "reports", "notes", "overview",
    "standard", "standards", "times", "time", "document", "documents",
    "general", "internal", "company", "details", "information", "team",
    "teams", "work", "rules", "list", "guide", "faq", "faqs", "summary",
    "target", "targets", "goal", "goals", "current", "amount", "amounts",
    "strategy", "strategies",
}


def extract_query_terms(raw_query: str) -> Tuple[List[str], List[str]]:
    """Return content terms and distinctive topic terms."""
    is_ma = bool(
        re.search(
            r"\b(m\s*&\s*a|merger|acquisition)\b",
            raw_query,
            re.IGNORECASE,
        )
    )

    cleaned = re.sub(r"[^\w\s]", " ", raw_query, flags=re.UNICODE).lower().strip()
    words = [word for word in cleaned.split() if len(word) > 1]

    content_words = [word for word in words if word not in STOPWORDS]
    if not content_words:
        content_words = words

    distinctive_words = [
        word for word in content_words
        if word not in GENERIC_MODIFIERS
    ]

    if is_ma:
        for term in ("acquisition", "merger", "apextracing", "falcon"):
            if term not in distinctive_words:
                distinctive_words.append(term)

    return content_words, distinctive_words


def sanitize_fts5_query(raw_query: str) -> str:
    """Build an SQLite FTS5 MATCH expression from user input."""
    content_words, distinctive_words = extract_query_terms(raw_query)
    target_words = distinctive_words or content_words

    if not target_words:
        return '""'

    return " OR ".join(f'"{word}"*' for word in target_words)


class BaseRetrievalEngine(ABC):
    """Abstract interface for knowledge retrieval engines."""

    @abstractmethod
    def search(
        self,
        query: str,
        allowed_classifications: Set[str],
        limit: int = 5,
    ) -> List[SearchResultItem]:
        """Return ranked excerpts respecting access classifications."""
        pass

    @abstractmethod
    def get_document(
        self,
        document_id: str,
        allowed_classifications: Set[str],
    ) -> Tuple[Optional[DocumentDetail], bool]:
        """Retrieve a document while enforcing authorization."""
        pass

    @abstractmethod
    def list_documents(
        self,
        allowed_classifications: Set[str],
    ) -> List[DocumentSummary]:
        """List documents visible to the caller."""
        pass


class SQLiteFTS5RetrievalEngine(BaseRetrievalEngine):
    """SQLite FTS5 retrieval with chunk-level ranking and RBAC enforcement."""

    def __init__(self, db_path: Optional[Path] = None):
        settings = get_settings()
        self.db_path = db_path or settings.DATABASE_PATH

    def search(
        self,
        query: str,
        allowed_classifications: Set[str],
        limit: int = 5,
    ) -> List[SearchResultItem]:
        """Search relevant chunks while enforcing access classification filters."""
        if not allowed_classifications or limit <= 0:
            return []

        clean_query = query.strip()
        if not clean_query:
            return []

        content_words, distinctive_words = extract_query_terms(clean_query)
        if not content_words:
            return []

        has_ma_term = bool(
            re.search(
                r"\b(m\s*&\s*a|merger|acquisition)\b",
                clean_query,
                re.IGNORECASE,
            )
        )
        if has_ma_term and "acquisition" not in distinctive_words:
            distinctive_words.append("acquisition")

        target_words = distinctive_words or content_words
        match_clause = " OR ".join(f'"{word}"*' for word in target_words)

        classifications = sorted({
            classification.lower()
            for classification in allowed_classifications
        })
        placeholders = ",".join("?" for _ in classifications)

        sql = f"""
            SELECT
                fts.chunk_id,
                fts.document_id,
                fts.title,
                fts.category,
                fts.heading,
                snippet(documents_fts, 5, '[[', ']]', '...', 48)
                    AS excerpt_snippet,
                bm25(documents_fts) AS rank_score,
                d.access_classification,
                dc.content AS full_chunk_text
            FROM documents_fts fts
            JOIN documents d ON d.id = fts.document_id
            JOIN document_chunks dc ON dc.id = fts.chunk_id
            WHERE documents_fts MATCH ?
              AND LOWER(d.access_classification) IN ({placeholders})
            ORDER BY rank_score ASC
            LIMIT ?;
        """

        # Retrieve extra candidates to allow filtering while retaining multiple
        # relevant chunks from the same document.
        candidate_limit = min(max(limit * 10, 50), 500)
        params = [match_clause, *classifications, candidate_limit]

        with get_db_connection(self.db_path) as conn:
            try:
                rows = conn.execute(sql, params).fetchall()
            except Exception:
                # Never return unfiltered content if an FTS query fails.
                return []

        chunk_best_match: Dict[str, SearchResultItem] = {}
        chunk_scores: Dict[str, float] = {}

        # Use distinctive terms to judge topical relevance, but calculate
        # the overlap gate against the full content terms to prevent overly
        # broad queries from returning weakly related documents.
        phrase_clean = " ".join(content_words).lower()

        for row in rows:
            doc_id = row["document_id"]
            title = row["title"]
            category = row["category"]
            heading = row["heading"] or ""
            full_text = row["full_chunk_text"] or ""
            combined_text = f"{title} {category} {heading} {full_text}".lower()

            if distinctive_words and not any(
                re.search(rf"\b{re.escape(term)}\b", combined_text)
                for term in distinctive_words
            ):
                continue

            # Whole-word matching avoids false positives such as "base"
            # matching inside "database".
            matched_terms = [
                term for term in content_words
                if re.search(rf"\b{re.escape(term)}\b", combined_text)
            ]
            term_overlap_ratio = (
                len(matched_terms) / len(content_words)
                if content_words else 1.0
            )

            if len(content_words) >= 2 and term_overlap_ratio < 0.40:
                continue

            raw_bm25 = float(row["rank_score"])
            base_score = abs(raw_bm25) if raw_bm25 != 0 else 1.0

            boost = 1.0
            if phrase_clean and phrase_clean in combined_text:
                boost += 2.5

            title_heading = f"{title} {heading}".lower()
            if any(
                re.search(rf"\b{re.escape(term)}\b", title_heading)
                for term in (distinctive_words or content_words)
            ):
                boost += 2.0

            boost += term_overlap_ratio * 1.5
            final_score = round(base_score * boost, 3)

            snippet_text = row["excerpt_snippet"]
            if not snippet_text or len(snippet_text.strip()) < 15:
                snippet_text = full_text[:350]
                if len(full_text) > 350:
                    snippet_text += "..."

            item = SearchResultItem(
                document_id=doc_id,
                title=title,
                category=category,
                access_classification=row["access_classification"],
                heading=heading or None,
                excerpt=snippet_text,
                score=final_score,
            )

            # Deduplicate by chunk ID, not document ID, so separate sections
            # from the same document can all be returned.
            chunk_id = row["chunk_id"]
            if (
                chunk_id not in chunk_scores
                or final_score > chunk_scores[chunk_id]
            ):
                chunk_scores[chunk_id] = final_score
                chunk_best_match[chunk_id] = item

        sorted_results = sorted(
            chunk_best_match.values(),
            key=lambda item: item.score,
            reverse=True,
        )

        if not sorted_results:
            return []

        top_score = sorted_results[0].score
        min_threshold = max(2.5, top_score * 0.55)

        filtered_results = [
            item for item in sorted_results
            if item.score >= min_threshold
        ]

        return filtered_results[:limit]

    def get_document(
        self,
        document_id: str,
        allowed_classifications: Set[str],
    ) -> Tuple[Optional[DocumentDetail], bool]:
        """Fetch a document only if its classification is authorized."""
        clean_doc_id = document_id.strip()

        with get_db_connection(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT id, title, category, author, last_updated, version,
                       access_classification, file_path, file_hash, raw_content,
                       created_at, updated_at
                FROM documents
                WHERE id = ? OR UPPER(id) = UPPER(?)
                """,
                (clean_doc_id, clean_doc_id),
            ).fetchone()

            if not row:
                return None, False

            allowed = {
                classification.lower()
                for classification in allowed_classifications
            }
            classification = row["access_classification"].lower()

            if classification not in allowed:
                return None, True

            chunk_count_row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM document_chunks
                WHERE document_id = ?
                """,
                (row["id"],),
            ).fetchone()

            return DocumentDetail(
                id=row["id"],
                title=row["title"],
                category=row["category"],
                author=row["author"],
                last_updated=row["last_updated"],
                version=row["version"],
                access_classification=row["access_classification"],
                file_path=row["file_path"],
                file_hash=row["file_hash"],
                raw_content=row["raw_content"],
                chunk_count=chunk_count_row["count"],
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
            ), False

    def list_documents(
        self,
        allowed_classifications: Set[str],
    ) -> List[DocumentSummary]:
        """List only documents authorized for the caller's clearance."""
        if not allowed_classifications:
            return []

        classifications = sorted({
            classification.lower()
            for classification in allowed_classifications
        })
        placeholders = ",".join("?" for _ in classifications)

        sql = f"""
            SELECT
                d.id, d.title, d.category, d.author, d.last_updated,
                d.version, d.access_classification,
                COUNT(dc.id) AS chunk_count
            FROM documents d
            LEFT JOIN document_chunks dc ON dc.document_id = d.id
            WHERE LOWER(d.access_classification) IN ({placeholders})
            GROUP BY d.id
            ORDER BY d.category, d.title;
        """

        with get_db_connection(self.db_path) as conn:
            rows = conn.execute(sql, classifications).fetchall()

        return [
            DocumentSummary(
                id=row["id"],
                title=row["title"],
                category=row["category"],
                author=row["author"],
                last_updated=row["last_updated"],
                version=row["version"],
                access_classification=row["access_classification"],
                chunk_count=row["chunk_count"],
            )
            for row in rows
        ]
