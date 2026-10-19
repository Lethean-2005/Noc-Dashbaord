"""Read/write access to the local incident_reports table — not a
Postgres/MSSQL sync cache. Holds Wholesale Products & Service Delivery
Incident Reports typed in via the Incident Report page; never auto-dropped
by init_cache_db() (see app/database/cache.py's own note on mentor_sites,
the same pattern this mirrors).
"""

import json

from app.database.cache import get_cache_conn

_COLUMNS = (
    "id",
    "document_title",
    "file_name",
    "incident_raised_by",
    "incident_received_by",
    "reported_date",
    "service_disruption",
    "incident_date",
    "report_time",
    "incident_number",
    "incident_category",
    "customers_impacted",
    "duration_of_interruption",
    "time_issue",
    "raise_time",
    "response_time",
    "restored_time",
    "details_date_and_time",
    "time_of_complaint",
    "issue_reported",
    "actions_taken_summary",
    "chronology_events_json",
    "cause_of_outage",
    "fault_gps_location",
    "issued_time",
    "resolution",
    "permanent_fixed",
    "has_second_fault",
    "cause_of_outage_2",
    "fault_gps_location_2",
    "issued_time_2",
    "resolution_2",
    "permanent_fixed_2",
    "improvement_plan_json",
    "picture_references_json",
    "status",
    "created_at",
    "updated_at",
)

# status isn't a field on the report form (parse_form() never produces
# it) — excluded from update()'s settable columns so a normal "Save
# Report" never overwrites it back to NULL. Only set_status() (the
# dedicated Mark Final / Revert to Draft actions) ever changes it.
_FORM_UPDATE_COLUMNS = [c for c in _COLUMNS if c not in ("id", "created_at", "status")]


class IncidentReportRepository:
    def create(self, report_id, fields, now):
        conn = get_cache_conn()
        try:
            values = {**fields, "id": report_id, "status": "Draft", "created_at": now, "updated_at": now}
            placeholders = ", ".join("?" for _ in _COLUMNS)
            conn.execute(
                f"INSERT INTO incident_reports ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
                [values.get(c) for c in _COLUMNS],
            )
            conn.commit()
        finally:
            conn.close()

    def update(self, report_id, fields, now):
        """Returns True if a row with this id existed and was updated.
        Never touches `status` — see _FORM_UPDATE_COLUMNS above."""
        conn = get_cache_conn()
        try:
            assignments = ", ".join(f"{c} = ?" for c in _FORM_UPDATE_COLUMNS)
            values = {**fields, "updated_at": now}
            cur = conn.execute(
                f"UPDATE incident_reports SET {assignments} WHERE id = ?",
                [values.get(c) for c in _FORM_UPDATE_COLUMNS] + [report_id],
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def set_status(self, report_id, status, now):
        """Returns True if a row with this id existed and was updated."""
        conn = get_cache_conn()
        try:
            cur = conn.execute(
                "UPDATE incident_reports SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, report_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def get(self, report_id):
        conn = get_cache_conn()
        try:
            row = conn.execute(
                "SELECT * FROM incident_reports WHERE id = ?", (report_id,)
            ).fetchone()
            return self._to_dict(row) if row else None
        finally:
            conn.close()

    def fetch_all(self):
        conn = get_cache_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM incident_reports ORDER BY updated_at DESC"
            ).fetchall()
            return [self._to_dict(r) for r in rows]
        finally:
            conn.close()

    def delete(self, report_id):
        conn = get_cache_conn()
        try:
            cur = conn.execute("DELETE FROM incident_reports WHERE id = ?", (report_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    @staticmethod
    def _to_dict(row):
        d = dict(row)
        d["chronology_events"] = json.loads(d.get("chronology_events_json") or "[]")
        d["improvement_plan"] = json.loads(d.get("improvement_plan_json") or "[]")
        d["picture_references"] = json.loads(d.get("picture_references_json") or "[]")
        return d
