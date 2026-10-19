"""Read/write access to the local Partner Contact cache
(instance/localstorage.db)."""

from app.database.cache import PARTNER_CONTACT_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class PartnerContactCacheRepository(BaseCacheRepository):
    valid_tables = PARTNER_CONTACT_CACHE_TABLES
    columns = (
        "partner_id",
        "contact_id",
        "partner_name",
        "partner_type",
        "domain",
        "escalation_level",
        "escalation_matrix",
        "contact_name",
        "contact_role",
        "phone_number",
        "email",
        "remark",
        "created_by",
        "created_at",
        "updated_by",
        "updated_at",
    )
    order_by = "partner_type, partner_name"
