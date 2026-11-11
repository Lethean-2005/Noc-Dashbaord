# Teams multi-site incident Excel attachment

## Current app behavior

The Site Down 24h alert groups rows by incident, counts each site code once,
and sends one message with one Excel workbook when two or more sites are impacted.
Single-site alerts remain text-only. The existing configured outage threshold
(default 24 hours) and restore-confirmation workflow are unchanged.

The workbook includes site name/code, RAN name, technology services, affected
services, province/district/commune, grade, VIP status, longitude and latitude.
Affected services currently uses the site technology inventory; this source does
not establish which individual radio technologies failed.

Workbook generation failures leave the incident eligible for a retry, rather
than recording an attachment-free multi-site message as successfully sent.
An HTTP 2xx response confirms webhook acceptance, not completion of the flow.

## Finish the existing Power Automate down-alert flow

The app already POSTs these fields together:

```json
{
  "text": "<HTML incident message>",
  "incident_ref": "INC-0000285049",
  "excel_filename": "Incident Report 3 Sites Down - INC-0000285049.xlsx",
  "excel_base64": "<base64 encoded XLSX>"
}
```

The Excel fields are optional and absent for single-site alerts and restore
messages. Preserve the existing text/incident_ref trigger fields and add the
optional Excel fields if the trigger has an explicit schema.

1. Add a condition before posting the down-alert:
   `not(empty(triggerBody()?['excel_base64']))`.
2. In the Yes branch, add SharePoint **Create file** in the destination Teams
   channel's document folder. Select the correct SharePoint site and folder
   from the connected account; private/shared channels can have separate sites.
   File Name: `triggerBody()?['excel_filename']`.
   File Content: `base64ToBinary(triggerBody()?['excel_base64'])`.
   Do not save the literal base64 text as an XLSX file.
3. Get the created file's properties/link. For a normal Teams message, include
   that file link after `triggerBody()?['text']`. Channel members must have access.
4. To show a native file attachment card like the reference screenshot, use a
   Teams/Graph action supported by the tenant that posts a reference attachment
   to the uploaded SharePoint file. A plain HTML hyperlink is not the same card.
   Microsoft documents the message body and attachment format here:
   https://learn.microsoft.com/en-us/graph/api/chatmessage-post#example-5-send-a-message-that-includes-a-file-attachment-using-a-file-share-link
   This requires a permitted authenticated action; it is not achieved by sending
   base64 directly to a Teams message webhook.
5. In the No branch, keep the existing text-only post.
6. In both branches, save the ID of the actual posted message to the existing
   incident_ref/Message ID ledger so restore replies still target that message.
   Handle failed uploads as failures rather than silently posting without a file.

Base64 conversion reference:
https://learn.microsoft.com/en-us/azure/logic-apps/workflow-definition-language-functions-reference#base64ToBinary

## Verification

Automated tests use mocked network sends. Before enabling a changed live flow,
verify a test incident with multiple sites: one message, correct distinct site
count, a workbook that opens in Excel, preserved leading zeroes in site codes,
and a restore reply linked to the original message. Also verify a single-site
incident without Excel fields. Inspect the flow run history for both branches.


## Restore replies: confirmed final rules

The Incident status explanation describes when Actual Root Cause and Resolution
are usually populated; it is not an additional status filter for replies.
Eligibility uses a valid source-specific start/end timestamp pair:

- Alarms/automatic: Issue Occurred At -> Cleared Alarm Received At. No fallback to Resolved At.
- NOC/manual/non-Alarms: Created At -> Closed At.

Missing or reversed pairs remain pending. No timestamp from a different field
is substituted. Source, rather than creation_method, selects the pair. UTC
source values are converted exactly once to Cambodia time.

Root Cause uses Actual Root Cause only; Action Recovery uses Resolution only.
Blank values display Not recorded. No suspected-cause or previous-comment
fallback is used. The reply matches the latest reference: Dear All, restoration sentence, incident
reference plus five restoration fields, and Best Regards / Work Flow Sitedown-alert.
The same incident_ref remains in the webhook payload for thread routing.


## Final workbook typography/layout

Teams/SharePoint Excel files start with the column headers in row 1, with no
merged Incident Report title or generated timestamp row. All populated cells
use Huawei Sans regular weight. Filter arrows and wrapping are disabled;
column widths fit header/record text, and headers remain frozen at A2.
Telegram generated images and Excel files also use Huawei Sans, retaining
Telegram's existing titles, filtering, schedules and destinations. Plain-text
Telegram messages use the Telegram client's own UI font.
