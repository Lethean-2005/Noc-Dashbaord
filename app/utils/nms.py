"""Shared NMS vendor-code -> vendor-name mapping (object_227.nms_name on
PostgreSQL). Used to be a `CASE nms_name WHEN 3 THEN 'ZTE' ...` block
copy-pasted across several SQL query files (incident_by_status.sql,
incwo_by_status.sql, incwo_site_down.sql, inprogress_wo_resolve.sql,
site_down.sql), plus a second, independent copy in vip_alarm_service.py.
Every query now selects the raw code and this one dict resolves it
wherever a display name is needed.
"""
NMS_NAMES = {"3": "ZTE", "5": "Huawei", "7": "Nokia"}
