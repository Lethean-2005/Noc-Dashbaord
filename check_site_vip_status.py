"""Checks whether a site's VIP/VVIP status agrees between Postgres
(object_160.site_strategic_type) and MSSQL (TBL_SITE.SITE_STRATEGIC) —
the two systems can drift apart (confirmed live for site 1517/CHI_PECH
on 2026-09-22: MSSQL said VIP, Postgres said none_strategic, and the
site's real Site Down incident never reached the VIP card because only
Postgres was trusted at the time — see vip_alarm_sync_service.py /
vip_incident_status.sql, which now check both).

Queries both databases live — not the local SQLite cache — so this
always reflects the current, real state of both systems, not whatever
was last synced.

Run directly:
    python check_site_vip_status.py 1517
    python check_site_vip_status.py 1517 5954 1608

No site code given checks every site MSSQL's TBL_SITE currently flags
VIP/VVIP against Postgres, to surface every current mismatch at once:
    python check_site_vip_status.py
"""

import sys

from app import create_app

_VIP_TYPES = ("vip", "vvip")


def _check_one(site_code):
    from sqlalchemy import text

    from app.database.mssql import _connect
    from app.extensions import db

    pg_row = (
        db.session.execute(
            text(
                """
                SELECT standard_code, name, site_strategic_type, status
                FROM object_160
                WHERE standard_code = :code
                """
            ),
            {"code": site_code},
        )
        .mappings()
        .first()
    )

    conn = _connect()
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT SITE_CODE, SITE_NAME, SITE_STRATEGIC, STATUS, IS_REMOVED "
            "FROM TBL_SITE WHERE SITE_CODE = %s",
            (site_code,),
        )
        mssql_rows = cur.fetchall()
    finally:
        conn.close()

    pg_type = (pg_row["site_strategic_type"] if pg_row else "") or "none_strategic"
    mssql_type = (mssql_rows[0]["SITE_STRATEGIC"] if mssql_rows else "") or "(not found)"

    pg_is_vip = pg_type.lower() in _VIP_TYPES
    mssql_is_vip = mssql_type.lower() in _VIP_TYPES
    agree = pg_is_vip == mssql_is_vip

    print(f"\n{'=' * 60}")
    print(f"Site {site_code}")
    print(f"{'=' * 60}")
    print(f"  Postgres (site_strategic_type): {pg_type!r:20} -> VIP/VVIP? {pg_is_vip}")
    print(f"  MSSQL    (SITE_STRATEGIC):      {mssql_type!r:20} -> VIP/VVIP? {mssql_is_vip}")
    if not pg_row:
        print("  ! not found in Postgres object_160 at all")
    if not mssql_rows:
        print("  ! not found in MSSQL TBL_SITE at all")
    print("  AGREE" if agree else "  *** MISMATCH ***")
    return agree


def main():
    app = create_app()
    with app.app_context():
        site_codes = sys.argv[1:]
        if not site_codes:
            from app.repositories.vip.vip_site_cache_repository import VipSiteCacheRepository

            rows = VipSiteCacheRepository().fetch_all("vip_site_cache")
            site_codes = sorted({r["site_code"] for r in rows if r.get("site_code")})
            print(f"No site code given — checking all {len(site_codes)} MSSQL VIP/VVIP sites...")

        mismatches = [code for code in site_codes if not _check_one(code)]

        print(f"\n{'=' * 60}")
        print(f"Checked {len(site_codes)} site(s), {len(mismatches)} mismatch(es).")
        if mismatches:
            print("Mismatched:", ", ".join(mismatches))


if __name__ == "__main__":
    main()
