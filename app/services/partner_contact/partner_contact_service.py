"""Business logic for the Partner Contact page's Create/Add Contact/Edit/
Delete actions. Reads stay on the local cache (see
app/routes/partner_contact.py's own cache repository) — only writes go
through here, straight to the real MSSQL tables (TBL_PARTNER /
TBL_PARTNER_CONTACT), same reasoning as
AlarmService.acknowledge_note()/clear_alarm(): the local cache is fully
replaced every sync cycle by partner_contact_sync_service.py, so a write
that only touched the cache would be silently reverted on the next sync
instead of actually persisting.

create_partner_with_contacts() makes a Partner and however many Contacts
were filled in on the Add Partner form together, in one submission —
a Partner is meant to have several Contacts (one per escalation level),
all sharing one PartnerID. add_contact() is the same idea for a Partner
that already exists: attaches one more Contact to it without creating a
duplicate Partner row with the same name.
"""

from app.repositories.partner_contact.partner_contact_repository import PartnerContactRepository


class PartnerContactService:
    def __init__(self, mssql_repository=None):
        self.mssql_repository = mssql_repository or PartnerContactRepository()

    def partner_name_exists(self, partner_name):
        """True if a Partner with this exact name (case-insensitive)
        already exists — checked before create_partner_with_contacts()
        so Add Partner can't create a second partner with the same name."""
        return self.mssql_repository.find_partner_by_name(partner_name)

    def find_partner_id_by_name(self, partner_name):
        """Returns the existing PartnerID for this name, or None — used by
        the Import flow to attach contacts to an already-existing partner
        instead of creating a duplicate one."""
        return self.mssql_repository.find_partner_id_by_name(partner_name)

    def create_partner_with_contacts(self, partner_name, partner_type, domain, username, contacts):
        """`domain` (e.g. "Telcotech"/"Cellcard") is required —
        TBL_PARTNER.Domain is NOT NULL with no default. `contacts` is a
        list of dicts (escalation_level, escalation_matrix, contact_name,
        contact_role, phone_number, email, remark) — see
        partner_contact.py's create(). Creates the Partner plus every
        one of them together, atomically."""
        return self.mssql_repository.create_partner_with_contacts(
            partner_name,
            partner_type,
            domain,
            username,
            contacts,
        )

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
        """Attaches a new Contact to a Partner that already exists —
        the "add another escalation-level contact without duplicating
        the partner" path (see this module's own docstring)."""
        return self.mssql_repository.add_contact(
            partner_id,
            escalation_level,
            escalation_matrix,
            contact_name,
            contact_role,
            phone_number,
            email,
            remark,
            username,
        )

    def update_partner(
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
        return self.mssql_repository.update(
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
        )

    def delete_contact(self, contact_id):
        return self.mssql_repository.delete(contact_id)
