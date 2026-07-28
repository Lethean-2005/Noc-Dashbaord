"""Read/write access to the local telegram_alert_cache
(instance/localstorage.db) — every Site Down incident found on the
Telegram alert's last run (app/services/telegram/telegram_alert.py)."""
from app.database.cache import TELEGRAM_ALERT_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class TelegramAlertCacheRepository(BaseCacheRepository):
    valid_tables = TELEGRAM_ALERT_CACHE_TABLES
    columns = ("incident_id", "incident_status", "wo_id", "wo_created_at", "wo_status",
               "site_name", "site_code", "occurred_at", "outage_min", "l1_noc_investigation_result",
               "last_comments", "nms", "hub_site", "site_grade", "province", "district", "commune")
    order_by = "occurred_at DESC"
