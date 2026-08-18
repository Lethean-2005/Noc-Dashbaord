# Telegram alert bots — which bot posts where

Four independent Telegram bots, each with its own token/chat-id pair in
`.env`, each posting to its own group/channel on VM. (Local `.env`
deliberately shares one test group across INC-WO Power/General — see
below.) Cross-wiring one alert's `TELEGRAM_CHAT_IDS_*` onto another's
group silently sends the wrong content into the wrong place.

Confirmed live via Telegram's own `getChat`/`getUpdates` API on
2026-08-14 (bot usernames only — never put a raw bot token in this file
or any other doc; get the live value from `.env`).

| Alert | Bot username | Env var (token) | Env var (chat id) |
|---|---|---|---|
| Site Down (4h) | `@streamline_sitedown_bot` | `TELEGRAM_BOT_TOKEN` | `TELEGRAM_CHAT_IDS` |
| INC-WO Site Down | `@INC_WO_SiteDownBot` | `TELEGRAM_BOT_INC_WO_TOKEN` | `TELEGRAM_CHAT_IDS_INC_WO` |
| INC-WO Power | `@INC_WO_PowerBot` | `TELEGRAM_BOT_INC_WO_POWER_TOKEN` | `TELEGRAM_CHAT_IDS_INC_WO_POWER` |
| INC-WO General | `@INC_WO_AlertBot` | `TELEGRAM_BOT_INC_WO_GENERAL_TOKEN` | `TELEGRAM_CHAT_IDS_INC_WO_GENERAL` |

## VM (production) chat ids

| Alert | Chat id | Group/channel name |
|---|---|---|
| Site Down (4h) | `-1004345641618` | Site Down Alert(Over 4Hours) |
| INC-WO Site Down | `-1004437332546` | TSE&C INC-WO Site Down Follow Up |
| INC-WO Power | `-1004482729871` | TSE&C INC-WO Power Follow Up |
| INC-WO General | `-1004312948998` | TSE&C INC-WO HW/TX Follow Up |

## INC-WO General — resolved to its real production channel

`-1004312948998` ("TSE&C INC-WO HW/TX Follow Up") was originally found
via `getUpdates` as a channel `@INC_WO_PowerBot` (a different bot) was
oddly a member of, with no `.env` var pointing at it. Its own Telegram
description confirms it's the right channel for this alert: *"This
channel use for follow up with sub-con for all INC-WO exclude incident
category 'Site Down' and 'Power'"* — an exact match for what
`telegram_inc_wo_general_alert.py` sends.

As of 2026-08-14, `@INC_WO_AlertBot` is confirmed a member (a live
`getChat` call now succeeds, where it previously returned "Bad Request:
chat not found") — VM's `.env` is set to this chat id. Local `.env` stays
on `-1004472362567` (the "INC_WO POWER" test supergroup) deliberately,
for dev-time testing without touching the real channel.
