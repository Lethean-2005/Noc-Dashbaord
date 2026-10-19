"""Data access for Partner Contact data (TBL_PARTNER / TBL_PARTNER_CONTACT)
on MSSQL."""

import uuid

from app.database.mssql import (
    run_mssql_batch_write,
    run_mssql_query,
    run_mssql_query_params,
    run_mssql_write,
    run_mssql_write_returning,
)


class PartnerContactRepository:
    def fetch_partner_contacts(self):
        return run_mssql_query("partner-contact", "partner_contact_cache")

    def find_partner_by_name(self, partner_name):
        """True if a Partner with this exact name (case-insensitive)
        already exists — Add Partner's duplicate check."""
        rows = run_mssql_query_params("partner-contact", "find_partner_by_name", (partner_name,))
        return bool(rows)

    def find_partner_id_by_name(self, partner_name):
        """Returns the existing PartnerID for this name (case-insensitive),
        or None — the Import flow's "partner already existed, attach
        contacts to it instead of creating a new one" path. Reuses the
        same find_partner_by_name query since it already selects PartnerID."""
        rows = run_mssql_query_params("partner-contact", "find_partner_by_name", (partner_name,))
        return str(rows[0]["PartnerID"]) if rows else None

    def create_partner_with_contacts(self, partner_name, partner_type, domain, username, contacts):
        """Creates a Partner and every Contact in `contacts` together as
        one atomic batch — everything commits together, or a failure
        partway through rolls it all back. `domain` (e.g.
        "Telcotech"/"Cellcard") is required — TBL_PARTNER.Domain is
        NOT NULL with no default. `contacts` is a list of dicts with keys
        escalation_level, escalation_matrix, contact_name, contact_role,
        phone_number, email, remark — remark/contact_role are
        Contact-level (TBL_PARTNER_CONTACT), not Partner-level, so
        there's no top-level `remark` param here. Returns the new
        partner_id."""
        partner_id = str(uuid.uuid4())
        steps = [
            ("insert_partner", (partner_id, partner_name, partner_type, domain, username)),
        ]
        for c in contacts:
            steps.append((
                "insert_contact",
                (
                    partner_id,
                    c["escalation_level"],
                    c["escalation_matrix"],
                    c["contact_name"],
                    c["contact_role"],
                    c["phone_number"],
                    c["email"],
                    c["remark"],
                    username,
                ),
            ))
        run_mssql_batch_write("partner-contact", steps)
        return partner_id

    def add_contact(
        self,
        partner_id,
        escalation_level,
        escalation_matrix,
        contact_name,
        contact_role,
        phone_number,
        email,
        remark,
        username,
    ):
        """Adds a new Contact to an existing Partner — never creates a
        new TBL_PARTNER row. Returns the new {'ContactID': ...} row, or
        None if nothing came back."""
        rows = run_mssql_write_returning(
            "partner-contact",
            "insert_contact",
            (
                partner_id,
                escalation_level,
                escalation_matrix,
                contact_name,
                contact_role,
                phone_number,
                email,
                remark,
                username,
            ),
        )
        return rows[0] if rows else None

    def update(
        self,
        partner_id,
        contact_id,
        partner_name,
        partner_type,
        escalation_level,
        escalation_matrix,
        contact_name,
        contact_role,
        phone_number,
        email,
        remark,
        username,
    ):
        """Updates the Partner and Contact rows together, atomically —
        matched by partner_id/contact_id, not name/type text. remark/
        contact_role are Contact-level, so they go to update_contact,
        not update_partner. Returns True only if both rows were found
        and updated."""
        rowcounts = run_mssql_batch_write(
            "partner-contact",
            [
                (
                    "update_partner",
                    (partner_name, partner_type, username, partner_id),
                ),
                (
                    "update_contact",
                    (
                        escalation_level,
                        escalation_matrix,
                        contact_name,
                        contact_role,
                        phone_number,
                        email,
                        remark,
                        username,
                        contact_id,
                    ),
                ),
            ],
        )
        return all(rc > 0 for rc in rowcounts)

    def delete(self, contact_id):
        """Deletes just this Contact row — the Partner row and its
        other contacts are left alone. Returns True if a row was removed."""
        rows_affected = run_mssql_write("partner-contact", "delete_contact", (contact_id,))
        return rows_affected > 0
