# JSON API v1

Open `/api/v1/` to list supported endpoints and methods. Map data is at `GET /api/v1/map/sites`; Mentor CSV validation is at `POST /api/v1/mentor/validate`. Partner Contact JSON endpoints appear under `/api/v1/partner-contact/`.

These routes share the existing handlers, response shapes, validation and service calls. Original URLs remain available. Pages, HTML fragments, redirects and file downloads keep their existing routes.

POST endpoints retain the original form or multipart file inputs, rather than introducing JSON request bodies. Browser requests must continue supplying the existing CSRF token. Import password checks and other validation remain in place. There is no new authentication mechanism or external API access policy.

GET `/api/v1/partner-contact/contacts` accepts `partner_id`; GET `/api/v1/partner-contact/check-name` accepts `name`. Mentor validation accepts a CSV upload in the multipart field `file` and does not save sites. Partner mutation endpoints write through the same existing services; consult their form fields before integration. The versioned API is an incremental URL migration, not a replacement of business rules.

Worker health is available at `GET /api/v1/system/sync`. It reads the local heartbeat only, returns `Cache-Control: no-store`, and never starts jobs. This is separate from the original 13 JSON route aliases.
