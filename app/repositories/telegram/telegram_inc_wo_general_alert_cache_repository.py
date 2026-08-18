"""Read/write access to the local telegram_inc_wo_general_alert_cache
(instance/localstorage.db) — every INC-WO General row found on the
Telegram INC-WO General alert's last run
(app/services/telegram/telegram_inc_wo_general_alert.py)."""

from app.database.cache import TELEGRAM_INC_WO_GENERAL_ALERT_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class TelegramIncWoGeneralAlertCacheRepository(BaseCacheRepository):
    valid_tables = TELEGRAM_INC_WO_GENERAL_ALERT_CACHE_TABLES
    columns = (
        "incident_id",
        "incident_status",
        "wo_id",
        "wo_created_at",
        "wo_status",
        "site_name",
        "site_code",
        "outage_min",
        "fault_description",
        "nms",
        "hub_site",
        "site_grade",
        "province",
        "district",
        "commune",
    )
    order_by = "wo_created_at DESC"
