"""Versioned JSON routes sharing the existing request handlers."""

from flask import Blueprint, current_app, jsonify, url_for

# Path, API endpoint, existing endpoint, method. Keep legacy URLs registered.
JSON_ROUTES = (
    ("/map/sites", "map_sites", "mapview.sites_json", "GET"),
    ("/mentor/validate", "mentor_validate", "mentor.validate_upload", "POST"),
    ("/partner-contact/contacts", "partner_contacts", "partner_contact.partner_contacts", "GET"),
    ("/partner-contact/domains", "partner_domains", "partner_contact.domains", "GET"),
    ("/partner-contact/escalation-levels", "partner_escalation_levels", "partner_contact.escalation_levels", "GET"),
    ("/partner-contact/escalation-matrix-values", "partner_escalation_matrix", "partner_contact.escalation_matrix_values", "GET"),
    ("/partner-contact/check-name", "partner_check_name", "partner_contact.check_name", "GET"),
    ("/partner-contact/verify-import-password", "partner_verify_import_password", "partner_contact.verify_import_password", "POST"),
    ("/partner-contact/import", "partner_import", "partner_contact.import_rows", "POST"),
    ("/partner-contact/create-partner-only", "partner_create", "partner_contact.create_partner_only", "POST"),
    ("/partner-contact/add-contact-only", "partner_add_contact", "partner_contact.add_contact_only", "POST"),
    ("/partner-contact/update-contact-only", "partner_update_contact", "partner_contact.update_contact_only", "POST"),
    ("/partner-contact/delete-contact-only", "partner_delete_contact", "partner_contact.delete_contact_only", "POST"),
)


def register_api(app):
    """Register after page blueprints so validation and behavior stay shared."""
    api = Blueprint("api_v1", __name__, url_prefix="/api/v1")

    @api.get("")
    @api.get("/")
    def index():
        return jsonify(
            version="v1",
            endpoints=[
                {"method": method, "url": url_for("api_v1." + endpoint)}
                for _, endpoint, _, method in JSON_ROUTES
            ] + [{"method": "GET", "url": url_for("api_v1.sync_status")}],
        )

    @api.get("/system/sync")
    def sync_status():
        from app.worker_runtime import read_worker_status

        response = jsonify(read_worker_status(current_app.instance_path))
        response.headers["Cache-Control"] = "no-store"
        return response

    for path, endpoint, existing, method in JSON_ROUTES:
        api.add_url_rule(path, endpoint, app.view_functions[existing], methods=[method])
    app.register_blueprint(api)
