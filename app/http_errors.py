"""Consistent browser and API responses for application HTTP errors."""
from flask import render_template, request, url_for
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException


_MESSAGES = {
    400: ("Please open the page again.", "We could not process this request. Open the page again and check your input."),
    401: ("Authentication is required.", "This resource requires authentication. Return to the dashboard or contact your administrator."),
    403: ("Access to this page is restricted.", "You do not have permission to access this resource. Contact your administrator if you need access."),
    404: ("We couldn't find that page.", "The address may be incorrect or the page may have moved. Return to the dashboard to continue."),
    405: ("This request method is not allowed.", "This address does not support that request method. Open the page using its navigation or form."),
    408: ("The request took too long.", "Check your connection, then open the page again and retry."),
    409: ("This record has changed.", "Open the latest version of the record and review your changes before trying again."),
    410: ("This resource is no longer available.", "Return to the dashboard to find the current page or record."),
    413: ("The uploaded file is too large.", "Choose a smaller file that meets the upload limit and try again."),
    415: ("This file or request format is not supported.", "Check the accepted format shown on the page and try again."),
    422: ("Please check the submitted information.", "Some information could not be processed. Review the form and try again."),
    429: ("Too many requests.", "Please wait before trying again."),
    500: ("Something went wrong on our end.", "An unexpected error occurred. Please try again later or return to the dashboard."),
    502: ("An upstream service could not respond correctly.", "A connected service may be temporarily unavailable. Please try again later."),
    503: ("The service is temporarily unavailable.", "Please try again later. If the issue continues, contact your administrator."),
    504: ("An upstream service took too long.", "A connected service did not respond in time. Please try again later."),
}


def register_error_handlers(app):
    @app.errorhandler(HTTPException)
    def http_error(error):
        code = error.code or 500
        # Preserve protocol headers, including Allow, WWW-Authenticate and Retry-After.
        response = error.get_response()
        title, message = _MESSAGES.get(code, (
            error.name, "This request could not be completed. Return to the dashboard or contact your administrator."
        ))
        if isinstance(error, CSRFError):
            title = "Please open the page again."
            message = ("Your form session is no longer available. Open the page again and retry. "
                       "This request was not processed.")
        wants_json = (
            request.path.startswith("/api/")
            or request.path == "/mentor/validate"
            or request.is_json
            or request.accept_mimetypes.best == "application/json"
        )
        if wants_json:
            response.set_data(app.json.dumps({"error": message}))
            response.mimetype = "application/json"
        else:
            mentor_request = request.path.startswith("/mentor/")
            response.set_data(render_template(
                "errors/http.html", code=code, name=error.name, title=title, message=message,
                return_url=url_for("mentor.index" if mentor_request else "dashboard.index"),
                return_label="Return to Mentor Site" if mentor_request else "Back to Home",
            ))
            response.mimetype = "text/html"
        response.headers["Cache-Control"] = "no-store"
        return response
