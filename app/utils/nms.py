"""Shared NMS vendor-code -> vendor-name mapping (object_227.nms_name on
PostgreSQL). Used to be a `CASE nms_name WHEN 3 THEN 'ZTE' ...` block
copy-pasted across several SQL query files (incident_by_status.sql,
inc_wo_by_status.sql, inc_wo_site_down.sql, inc_wo_resolved.sql,
incident_site_down.sql), plus a second, independent copy in vip_alarm_service.py.
Every query now selects the raw code and this one dict resolves it
wherever a display name is needed.
"""

NMS_NAMES = {"3": "ZTE", "5": "Huawei", "7": "Nokia"}

# object_160.actual_ran_vendor uses its own, different numeric codes (not
# NMS_NAMES' scheme) for the same three vendors — each code is actually
# the record ID of a Counterparty in Streamline's own
# counterparties_catalog (prd-web-mc.cellcard.com.kh/counterparties_catalog/
# form/<code>). This mapping was rewritten 2026-08-27 — the previous
# version (21->Nokia, 22->Huawei) was validated by cross-referencing
# against ape_alarm.nms (live alarm data), which turned out to be an
# unreliable signal (likely biased toward whichever vendor's equipment
# alarms more often, not actual fleet share) — it disagreed badly with
# Streamline's own data once checked directly.
#
# 7 = Nokia, 6 = ZTE, 20 = Huawei: each confirmed by an exact on-air
# site-count match between Streamline's own UI filter (Status='On Air'
# AND Actual RAN Vendor=<name>) and COUNT(*) FROM site_cache WHERE
# status='on_air' GROUP BY actual_ran_vendor in this app's cache (125,
# 516, and 1,272 respectively, on both sides).
#
# Codes 21 and 22 are ALSO Counterparty catalog records (object_170)
# literally named "Huawei" (21: type 'brand', 22: type 'vendor') — but
# they're deliberately left OUT of this mapping: Streamline's own
# "Actual RAN Vendor = Huawei" filter counts neither of them (confirmed
# 2026-08-27 — only code 20 exact-matched that filter's 1,272), so
# whatever they actually represent, Streamline itself doesn't treat them
# as interchangeable with code 20's "Huawei" for this field, and neither
# should this mapping — sharing a display name isn't enough evidence on
# its own once it's been checked against the real counted behavior and
# disagreed. Do not add them without checking against Streamline's own
# counts again, the same way 20/7/6 were confirmed.
#
# Maps straight to the equivalent NMS_NAMES key, not the vendor name, so
# existing NMS_NAMES.get(...) translation call sites need no changes —
# see incident_sync_service.py's _nms_by_site().
ACTUAL_RAN_VENDOR_TO_NMS_CODE = {20: "5", 7: "7", 6: "3"}


def resolve_nms_code_by_site(ne_rows, actual_ran_vendor_rows, use_ne_fallback=True):
    """site_code -> raw NMS vendor code (NMS_NAMES' own scheme), merging
    both confidence tiers above in priority order — the one shared
    implementation every consumer (incident_sync_service.py,
    map_view_service.py, ...) calls, so this logic lives in exactly one
    place instead of being copy-pasted and risking drift between them.

    1. actual_ran_vendor_rows, filtered through ACTUAL_RAN_VENDOR_TO_NMS_CODE
       — only the 3 codes confirmed correct against Streamline's own data.
    2. ne_rows (ne_nms_lookup_cache / object_227, "lowest NE id wins") —
       a DIFFERENT, independent signal (which NMS management system is
       configured on the equipment, not Streamline's own "Actual RAN
       Vendor" field) used as a fallback for every site tier 1 doesn't
       cover. Can disagree with what Streamline's own field would say —
       confirmed 2026-08-27 on the Map page: with this fallback on, the
       vendor counts among on-air sites didn't exactly match Streamline's
       own per-vendor filtered counts (e.g. Huawei read 1,456 instead of
       Streamline's 1,272 — the extra ~184 were tier-2 guesses, not
       confirmed data). Pass use_ne_fallback=False to skip this tier
       entirely and only ever return confirmed-tier-1 codes, when an
       exact match to Streamline's own counts matters more than covering
       every site — see map_view_service.py's own use of this flag.

    `ne_rows`: [{"site_code": ..., "nms_code": ...}, ...]
    `actual_ran_vendor_rows`: [{"site_code": ..., "actual_ran_vendor": ...}, ...]
    """
    nms_by_site = {r["site_code"]: r["nms_code"] for r in ne_rows} if use_ne_fallback else {}

    for r in actual_ran_vendor_rows:
        nms_code = ACTUAL_RAN_VENDOR_TO_NMS_CODE.get(r.get("actual_ran_vendor"))
        if nms_code:
            nms_by_site[r["site_code"]] = nms_code

    return nms_by_site
