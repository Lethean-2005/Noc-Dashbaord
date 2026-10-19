"""Pulls Partner Contact data from MSSQL (TBL_PARTNER / TBL_PARTNER_CONTACT
ONLY — TBL_PARTNER_CIRCUIT is not part of this cache, see
partner-contact.sql's partner_contact_cache query) and writes it into the
local cache (instance/localstorage.db). Mirrors pop_sync_service.py.
"""

from app.repositories.partner_contact.partner_contact_cache_repository import (
    PartnerContactCacheRepository,
)
from app.repositories.partner_contact.partner_contact_repository import (
    PartnerContactRepository,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

_TABLE = "partner_contact_cache"


class PartnerContactSyncService:
    def __init__(self, mssql_repository=None, cache_repository=None):
        self.mssql_repository = mssql_repository or PartnerContactRepository()
        self.cache_repository = cache_repository or PartnerContactCacheRepository()

    def sync(self):
        """Refresh the local Partner Contact cache from MSSQL. Returns the
        row count synced, or None on failure."""
        try:
            rows = self.mssql_repository.fetch_partner_contacts()
        except Exception as e:
            logger.error(f"MSSQL Partner Contact sync failed: {e}")
            return None

        normalized = [self._normalize(r) for r in rows]
        try:
            self.cache_repository.replace_all(_TABLE, normalized)
        except Exception as e:
            logger.error(f"Partner Contact cache write failed: {e}")
            return None
        logger.info(f"Synced {len(normalized)} row(s) into {_TABLE}")
        return len(normalized)

    @staticmethod
    def _normalize(row):
        # PartnerID/ContactID come back from pymssql as uuid.UUID objects
        # (uniqueidentifier columns), not strings — sqlite3 can't bind a
        # UUID object directly, so this must stringify them before they
        # ever reach the cache write.
        return {
            "partner_id": str(row["PartnerID"]) if row.get("PartnerID") else "",
            "contact_id": str(row["ContactID"]) if row.get("ContactID") else "",
            "partner_name": row.get("PartnerName") or "",
            "partner_type": row.get("PartnerType") or "",
            "domain": row.get("Domain") or "",
            "escalation_level": row.get("EscalationLevel") or "",
            "escalation_matrix": row.get("EscalationMatrix") or "",
            "contact_name": row.get("ContactName") or "",
            "contact_role": row.get("ContactRole") or "",
            "phone_number": row.get("PhoneNumber") or "",
            "email": row.get("Email") or "",
            "remark": row.get("Remark") or "",
            "created_by": row.get("CreatedBy") or "",
            "created_at": str(row["CreatedAt"]) if row.get("CreatedAt") else "",
            "updated_by": row.get("UpdatedBy") or "",
            "updated_at": str(row["UpdatedAt"]) if row.get("UpdatedAt") else "",
        }
