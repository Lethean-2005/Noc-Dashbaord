# Site Down Alarm List

This is the exact, fixed list of alarm event names this dashboard treats as **"Site Down"** — meaning the radio equipment itself has gone completely silent/unreachable, not just one subsystem alarming.

An alarm counts as "Site Down" only if its event name is an **exact match** (case-insensitive) to one of these — not a substring or a similar-sounding alarm. Anything else, no matter how serious, is bucketed as **"Other"**.

Used by:
- `app/utils/alarm_category.py` (`SITE_DOWN_EVENTS`) — the single shared source of this list
- VVIP Site card (`app/services/vip/vip_alarm_service.py`)
- Mentor Site card (`app/services/mentor/mentor_site_service.py`)
- RAN Status card's "completely down vs partially down" split (`alarm_completely_site_down_service.py`, `ran_site_down_service.py`, `ran_tech_down_service.py`)

## The list, by radio generation

| Alarm Event Name | Technology |
|---|---|
| NE is Disconnected | SRAN (shared baseband — takes down every generation at the site) |
| NE3SWS Agent not responding to requests | SRAN |
| The link between the server and the ME is broken | SRAN |
| gNodeB out of service | 5G |
| gNodeB DU out-of-service | 5G |
| eNodeB out of service | 4G |
| eNodeB is out of service | 4G |
| NodeB out of service | 3G |
| NodeB is out of service | 3G |
| WCDMA Base Station out of use | 3G |
| CSL Fault | 2G |
| BTS O&M Link Failure | 2G |
| Site Abis Control Link Broken | 2G |

**SRAN** (Single RAN) alarms are special — since one shared baseband serves every radio generation at a site, an SRAN alarm is treated as taking the *entire* site down, not just one technology.

## Why this list matters

A site can have very serious alarms (e.g. "SCTP Link Fault," "IP PM Activation Failure," "Cabinet Door Alarm") that are **not** on this list — those are real problems, but they land under "Other" because the equipment itself isn't reported as fully unreachable. This is a deliberate distinction: "Site Down" is reserved for a full outage, not every alarm severity level.

## Known gap (as of 2026-09-22)

A VIP/VVIP site's alarm can be a real formal outage (with its own Incident/Work Order and a team-wide notification) while still landing under "Other" here, if the specific alarm firing isn't on this list. Confirmed live for site CHIPHAT (1439, Koh Kong) on 2026-09-22 — a real VIP outage (INC-WO-SD-0110651) was driven by alarms like "IP PM Activation Failure" and "SCTP Link Fault," neither of which match this list, so it never appeared under the "Site Down" badge on either this dashboard or Streamline's own native one.
