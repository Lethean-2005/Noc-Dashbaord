-- name: partner_contact_cache
-- Partner + Contact only — TBL_PARTNER_CIRCUIT is not used anywhere in
-- this app (removed along with the "Manage Circuits" page). Remark and
-- ContactRole both come from TBL_PARTNER_CONTACT (per-contact), NOT
-- TBL_PARTNER — TBL_PARTNER.Remark exists too but is a separate,
-- unrelated column this app doesn't read/write. Domain IS from
-- TBL_PARTNER (e.g. "Telcotech"/"Cellcard") — powers index.html's
-- domain tabs (read-only here, not editable via Add/Edit Partner).
SELECT

    tp.PartnerID,
    tpc.ContactID,
    tp.PartnerName,
    tp.PartnerType,
    tp.Domain,

    tpc.EscalationLevel,
    tpc.EscalationMatrix,
    tpc.ContactName,
    tpc.ContactRole,
    tpc.PhoneNumber,
    tpc.Email,

    tpc.Remark,

    tpc.CreatedBy,
    tpc.CreatedAt,
    tpc.UpdatedBy,
    tpc.UpdatedAt

FROM TBL_PARTNER tp

LEFT JOIN TBL_PARTNER_CONTACT tpc
    ON tp.PartnerID = tpc.PartnerID

ORDER BY
    tp.PartnerType,
    tp.PartnerName,
    tpc.EscalationLevel;

-- name: find_partner_by_name
-- Add Partner's duplicate check (see PartnerContactService.partner_name_exists)
-- — UPPER() on both sides makes the match case-insensitive regardless of
-- the database's own collation setting. Queried live against MSSQL, not
-- the local cache, so a change made seconds ago by someone else (before
-- the next scheduled sync) is still caught.
SELECT TOP 1 PartnerID FROM TBL_PARTNER WHERE UPPER(PartnerName) = UPPER(%s);

-- name: insert_partner
-- Creates a Partner row alone. PartnerID is generated in PYTHON (not
-- SQL-side NEWID(), unlike insert_contact's ContactID below) so the same
-- id can be reused as a plain literal parameter across this insert AND
-- every insert_contact call that follows it in the same
-- run_mssql_batch_write() transaction (see
-- PartnerContactRepository.create_partner_with_contacts()) — a value a
-- step's own SQL generates server-side (NEWID()) isn't available to
-- steps after it, since run_mssql_batch_write() takes every step's
-- params upfront as one list, not one round trip at a time.
-- No Remark here — that field is Contact-level (TBL_PARTNER_CONTACT.Remark,
-- see insert_contact below), not Partner-level. Domain IS required here
-- (TBL_PARTNER.Domain is NOT NULL, no default — confirmed live via
-- INFORMATION_SCHEMA.COLUMNS; omitting it 515s "Cannot insert the value
-- NULL into column 'Domain'").
INSERT INTO TBL_PARTNER (PartnerID, PartnerName, PartnerType, Domain, Status, CreatedBy, CreatedAt)
VALUES (%s, %s, %s, %s, 'Active', %s, SYSUTCDATETIME());

-- name: insert_contact
-- Adds one new Contact to a Partner that already exists — unlike
-- create_partner_and_contact above, this never touches TBL_PARTNER at
-- all. Lets a partner end up with multiple escalation-level contacts
-- (L1/L2/L3/...) sharing one PartnerID, instead of every new contact
-- needing its own duplicate Partner row.
DECLARE @NewContactID uniqueidentifier = NEWID();

INSERT INTO TBL_PARTNER_CONTACT
    (ContactID, PartnerID, EscalationLevel, EscalationMatrix, ContactName, ContactRole, PhoneNumber, Email, Remark, IsActive, CreatedBy, CreatedAt)
VALUES (@NewContactID, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, SYSUTCDATETIME());

SELECT @NewContactID AS ContactID;

-- name: update_partner
-- No Remark here — see insert_partner's comment above.
UPDATE TBL_PARTNER
SET PartnerName = %s, PartnerType = %s, UpdatedBy = %s, UpdatedAt = SYSUTCDATETIME()
WHERE PartnerID = %s;

-- name: update_contact
UPDATE TBL_PARTNER_CONTACT
SET EscalationLevel = %s, EscalationMatrix = %s, ContactName = %s, ContactRole = %s, PhoneNumber = %s,
    Email = %s, Remark = %s, UpdatedBy = %s, UpdatedAt = SYSUTCDATETIME()
WHERE ContactID = %s;

-- name: delete_contact
-- Removes just this Contact row — the Partner row and any other
-- escalation-level Contact rows for the same partner are left alone.
DELETE FROM TBL_PARTNER_CONTACT WHERE ContactID = %s;
