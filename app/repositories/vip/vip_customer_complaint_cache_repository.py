"""Read/write access to the local vip_customer_complaint cache
(instance/localstorage.db)."""
from app.database.cache import VIP_CUSTOMER_COMPLAINT_CACHE_TABLES
from app.repositories.base_cache_repository import BaseCacheRepository


class VipCustomerComplaintCacheRepository(BaseCacheRepository):
    valid_tables = VIP_CUSTOMER_COMPLAINT_CACHE_TABLES
    columns = ("incident_id", "customer_address", "customer_phone_no",
               "problem_experienced_at", "fault_description")
    order_by = "problem_experienced_at DESC"
