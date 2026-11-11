"""Persistent user exclusions, independent of alarm-cache replacement."""
from app.database.cache import get_cache_conn


class CongestionBlacklistRepository:
    def fetch_all(self):
        conn = get_cache_conn()
        try:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM congestion_blacklist ORDER BY created_at DESC, id DESC"
            ).fetchall()]
        finally:
            conn.close()

    def add(self, rule):
        conn = get_cache_conn()
        try:
            conn.execute(
                "INSERT INTO congestion_blacklist "
                "(source, match_kind, match_value, pop_name, pop_code, device_name, ip_address, created_at, created_by, interface, additional_info, note, remark) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(source, match_kind, match_value) DO NOTHING",
                tuple(rule[key] for key in ("source", "match_kind", "match_value", "pop_name", "pop_code", "device_name", "ip_address", "created_at", "created_by", "interface", "additional_info", "note", "remark")),
            )
            conn.commit()
        finally:
            conn.close()

    def remove(self, rule_id):
        conn = get_cache_conn()
        try:
            conn.execute("DELETE FROM congestion_blacklist WHERE id = ?", (rule_id,))
            conn.commit()
        finally:
            conn.close()
