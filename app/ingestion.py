"""Document ingestion, chunking, metadata validation, and incremental synchronization."""

import hashlib
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import frontmatter
from pydantic import ValidationError

from app.config import get_settings
from app.database import get_db_connection
from app.models import DocumentChunk, DocumentFrontmatter, SyncResult

logger = logging.getLogger(__name__)


def compute_file_sha256(file_path: Path) -> str:
    """Calculate the SHA-256 hash of a file for change detection."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def chunk_markdown_content(doc_id: str, content: str, title: str) -> List[DocumentChunk]:
    """
    Split markdown document content into semantically coherent chunks based on headings
    and paragraph boundaries.
    """
    settings = get_settings()
    max_words = settings.CHUNK_SIZE_WORDS
    overlap_words = settings.CHUNK_OVERLAP_WORDS

    # Match markdown headings (# Heading, ## Heading, ### Heading)
    heading_pattern = re.compile(r"^(#{1,4}\s+.+)$", re.MULTILINE)
    parts = heading_pattern.split(content)

    sections: List[Tuple[str, str]] = []
    current_heading = title

    i = 0
    while i < len(parts):
        part = parts[i].strip()
        if not part:
            i += 1
            continue
        if heading_pattern.match(part):
            current_heading = part.lstrip("#").strip()
            # The next part should be the content under this heading
            if i + 1 < len(parts):
                section_text = parts[i + 1].strip()
                if section_text:
                    sections.append((current_heading, section_text))
                i += 2
                continue
            else:
                i += 1
                continue
        else:
            sections.append((current_heading, part))
            i += 1

    chunks: List[DocumentChunk] = []
    chunk_index = 0

    for heading, section_text in sections:
        words = section_text.split()
        if not words:
            continue

        if len(words) <= max_words:
            chunks.append(
                DocumentChunk(
                    id=f"{doc_id}-chunk-{chunk_index}",
                    document_id=doc_id,
                    chunk_index=chunk_index,
                    heading=heading,
                    content=section_text,
                )
            )
            chunk_index += 1
        else:
            # Sub-chunking long sections with overlap
            start = 0
            while start < len(words):
                end = min(start + max_words, len(words))
                sub_words = words[start:end]
                sub_text = " ".join(sub_words)
                chunks.append(
                    DocumentChunk(
                        id=f"{doc_id}-chunk-{chunk_index}",
                        document_id=doc_id,
                        chunk_index=chunk_index,
                        heading=heading,
                        content=sub_text,
                    )
                )
                chunk_index += 1
                if end == len(words):
                    break
                start += max_words - overlap_words

    # If document had no headings or empty sections, fallback to whole body
    if not chunks and content.strip():
        chunks.append(
            DocumentChunk(
                id=f"{doc_id}-chunk-0",
                document_id=doc_id,
                chunk_index=0,
                heading=title,
                content=content.strip(),
            )
        )

    return chunks


class IngestionEngine:
    """Manages document discovery, validation, and incremental synchronization into SQLite."""

    def __init__(self, knowledge_dir: Optional[Path] = None, db_path: Optional[Path] = None):
        settings = get_settings()
        self.knowledge_dir = knowledge_dir or settings.KNOWLEDGE_DIR
        self.db_path = db_path or settings.DATABASE_PATH

    def parse_document(self, file_path: Path) -> Tuple[DocumentFrontmatter, str, str]:
        """
        Parse markdown file, validate metadata frontmatter, compute SHA-256 hash.
        Returns: (metadata, body_content, sha256_hash)
        """
        raw_text = file_path.read_text(encoding="utf-8")
        parsed = frontmatter.loads(raw_text)
        metadata_dict = dict(parsed.metadata)

        # Validate through Pydantic
        try:
            metadata = DocumentFrontmatter(**metadata_dict)
        except ValidationError as e:
            raise ValueError(f"Invalid metadata in {file_path.name}: {e}")

        file_hash = compute_file_sha256(file_path)
        body = parsed.content
        return metadata, body, file_hash

    def sync(self) -> SyncResult:
        """
        Execute an incremental sync between the knowledge directory and the database.
        Detects new, modified, unchanged, and deleted documents.
        """
        result = SyncResult(status="success")
        if not self.knowledge_dir.exists():
            error_msg = f"Knowledge directory '{self.knowledge_dir}' does not exist."
            logger.error(error_msg)
            result.status = "partial_failure"
            result.errors.append(error_msg)
            return result

        md_files = list(self.knowledge_dir.glob("*.md"))
        disk_files_by_path: Dict[str, Path] = {
            str(p.resolve()): p for p in md_files
        }

        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # Retrieve existing documents from DB
            cursor.execute("SELECT id, file_path, file_hash FROM documents")
            db_docs = cursor.fetchall()
            db_docs_by_path: Dict[str, Tuple[str, str]] = {
                row["file_path"]: (row["id"], row["file_hash"]) for row in db_docs
            }

            # 1. Handle Deleted Documents (exist in DB, not on disk)
            deleted_paths: Set[str] = set(db_docs_by_path.keys()) - set(disk_files_by_path.keys())
            for del_path in deleted_paths:
                doc_id, _ = db_docs_by_path[del_path]
                logger.info(f"Removing deleted document: {doc_id} ({del_path})")
                cursor.execute("DELETE FROM documents_fts WHERE document_id = ?", (doc_id,))
                cursor.execute("DELETE FROM document_chunks WHERE document_id = ?", (doc_id,))
                cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
                result.deleted += 1

            # 2. Process Files on Disk (New, Modified, Unchanged)
            for path_str, file_path in disk_files_by_path.items():
                try:
                    metadata, body, file_hash = self.parse_document(file_path)
                except Exception as ex:
                    err = f"Failed to parse {file_path.name}: {str(ex)}"
                    logger.error(err)
                    result.errors.append(err)
                    continue

                if path_str not in db_docs_by_path:
                    # New document
                    try:
                        self._insert_document(cursor, metadata, path_str, file_hash, body)
                        result.added += 1
                        logger.info(f"Ingested new document: {metadata.id} ({file_path.name})")
                    except Exception as ex:
                        err = f"Failed inserting {metadata.id}: {str(ex)}"
                        logger.error(err)
                        result.errors.append(err)
                else:
                    existing_id, existing_hash = db_docs_by_path[path_str]
                    if existing_hash != file_hash or existing_id != metadata.id:
                        # Modified document
                        try:
                            self._update_document(cursor, metadata, path_str, file_hash, body, existing_id)
                            result.modified += 1
                            logger.info(f"Updated modified document: {metadata.id} ({file_path.name})")
                        except Exception as ex:
                            err = f"Failed updating {metadata.id}: {str(ex)}"
                            logger.error(err)
                            result.errors.append(err)
                    else:
                        # Unchanged
                        result.unchanged += 1

            # Commit all changes atomically
            conn.commit()

            # Record total documents count
            cursor.execute("SELECT COUNT(*) as count FROM documents")
            result.total_documents = cursor.fetchone()["count"]

            if result.errors:
                result.status = "partial_failure"

            # Record in sync_history
            cursor.execute(
                """
                INSERT INTO sync_history (status, added, modified, deleted, unchanged, total_documents, errors)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.status,
                    result.added,
                    result.modified,
                    result.deleted,
                    result.unchanged,
                    result.total_documents,
                    "; ".join(result.errors) if result.errors else None,
                ),
            )
            conn.commit()

        return result

    def _insert_document(
        self,
        cursor,
        meta: DocumentFrontmatter,
        file_path: str,
        file_hash: str,
        body: str,
    ) -> None:
        """Insert document record, chunks, and FTS5 entries."""
        cursor.execute(
            """
            INSERT INTO documents (
                id, title, category, author, last_updated, version,
                access_classification, file_path, file_hash, raw_content
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                meta.id,
                meta.title,
                meta.category,
                meta.author,
                meta.last_updated,
                meta.version,
                meta.access_classification.strip().lower(),
                file_path,
                file_hash,
                body,
            ),
        )

        chunks = chunk_markdown_content(meta.id, body, meta.title)
        for chunk in chunks:
            cursor.execute(
                """
                INSERT INTO document_chunks (id, document_id, chunk_index, heading, content)
                VALUES (?, ?, ?, ?, ?)
                """,
                (chunk.id, chunk.document_id, chunk.chunk_index, chunk.heading, chunk.content),
            )
            cursor.execute(
                """
                INSERT INTO documents_fts (chunk_id, document_id, title, category, heading, content)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (chunk.id, chunk.document_id, meta.title, meta.category, chunk.heading, chunk.content),
            )

    def _update_document(
        self,
        cursor,
        meta: DocumentFrontmatter,
        file_path: str,
        file_hash: str,
        body: str,
        existing_id: str,
    ) -> None:
        """Update existing document, replace its chunks and refresh FTS5 index."""
        # Clean previous chunks & FTS records
        cursor.execute("DELETE FROM documents_fts WHERE document_id = ?", (existing_id,))
        cursor.execute("DELETE FROM document_chunks WHERE document_id = ?", (existing_id,))

        cursor.execute(
            """
            UPDATE documents
            SET id = ?, title = ?, category = ?, author = ?, last_updated = ?,
                version = ?, access_classification = ?, file_hash = ?,
                raw_content = ?, updated_at = CURRENT_TIMESTAMP
            WHERE file_path = ?
            """,
            (
                meta.id,
                meta.title,
                meta.category,
                meta.author,
                meta.last_updated,
                meta.version,
                meta.access_classification.strip().lower(),
                file_hash,
                body,
                file_path,
            ),
        )

        chunks = chunk_markdown_content(meta.id, body, meta.title)
        for chunk in chunks:
            cursor.execute(
                """
                INSERT INTO document_chunks (id, document_id, chunk_index, heading, content)
                VALUES (?, ?, ?, ?, ?)
                """,
                (chunk.id, chunk.document_id, chunk.chunk_index, chunk.heading, chunk.content),
            )
            cursor.execute(
                """
                INSERT INTO documents_fts (chunk_id, document_id, title, category, heading, content)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (chunk.id, chunk.document_id, meta.title, meta.category, chunk.heading, chunk.content),
            )
