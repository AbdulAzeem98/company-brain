"""Thread-safe synchronization service with concurrency locking and status tracking."""

import asyncio
import logging
from typing import Optional
from fastapi import HTTPException, status

from app.ingestion import IngestionEngine
from app.models import SyncResult, SyncStatusResponse

logger = logging.getLogger(__name__)


class SyncService:
    """Manages knowledge synchronization with concurrency guards and status audit."""

    def __init__(self, ingestion_engine: Optional[IngestionEngine] = None):
        self.ingestion = ingestion_engine or IngestionEngine()
        self._lock = asyncio.Lock()
        self._is_syncing = False
        self._last_result: Optional[SyncResult] = None

    @property
    def is_syncing(self) -> bool:
        return self._is_syncing

    def get_status(self) -> SyncStatusResponse:
        """Return real-time synchronization state and previous sync statistics."""
        return SyncStatusResponse(
            is_syncing=self._is_syncing,
            last_sync=self._last_result,
        )

    async def trigger_sync(self) -> SyncResult:
        """
        Trigger an incremental sync operation.
        Guarded by an asyncio Lock to prevent concurrent execution from corrupting the index.
        """
        if self._lock.locked() or self._is_syncing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A knowledge synchronization job is already running. Concurrent refreshes are locked.",
            )

        async with self._lock:
            self._is_syncing = True
            logger.info("Starting knowledge base incremental synchronization...")
            try:
                # Run the synchronous SQLite ingestion in a thread pool to avoid blocking async loop
                result = await asyncio.to_thread(self.ingestion.sync)
                self._last_result = result
                logger.info(f"Sync completed: added={result.added}, modified={result.modified}, deleted={result.deleted}")
                return result
            except Exception as e:
                err_msg = f"Fatal sync error: {str(e)}"
                logger.error(err_msg, exc_info=True)
                result = SyncResult(status="failed", errors=[err_msg])
                self._last_result = result
                return result
            finally:
                self._is_syncing = False


# Global singleton instance
_sync_service_instance: Optional[SyncService] = None


def get_sync_service() -> SyncService:
    """Return singleton SyncService instance."""
    global _sync_service_instance
    if _sync_service_instance is None:
        _sync_service_instance = SyncService()
    return _sync_service_instance
