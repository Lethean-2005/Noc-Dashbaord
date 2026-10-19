"""Pulls the SLA policy/threshold table (object_327) from PostgreSQL into
the local cache (instance/localstorage.db). A single small (80-row)
reference table, so no per-table inventory docstring needed like
incident_sync_service.py's — this is the whole class. Mirrors that
module's own retry_fetch()/try-except-log convention."""

from app.repositories.sla_policy.sla_policy_cache_repository import SlaPolicyCacheRepository
from app.repositories.sla_policy.sla_policy_repository import SlaPolicyRepository
from app.services.postgres_sync_utils import retry_fetch
from app.utils.logger import get_logger

logger = get_logger(__name__)

_SLA_POLICY_TABLE = "sla_policy"


class SlaPolicySyncService:
    def __init__(self, repository=None, cache_repository=None):
        self.repository = repository or SlaPolicyRepository()
        self.cache_repository = cache_repository or SlaPolicyCacheRepository()

    def sync(self):
        rows = retry_fetch(self.repository.fetch_all, "SLA-policy")
        if rows is None:
            return None
        try:
            self.cache_repository.replace_all(_SLA_POLICY_TABLE, rows)
        except Exception as e:
            logger.error(f"SLA-policy cache write failed: {e}")
            return None
        logger.info(f"Synced {len(rows)} row(s) into {_SLA_POLICY_TABLE}")
        return len(rows)
