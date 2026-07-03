# NYRR Race + Volunteer Spot Watcher

Emails you when a **9+1-credit** NYRR race entry or volunteer slot opens up —
including spots that free up after something sold out. Runs free on GitHub
Actions roughly every 30 minutes. No server to maintain.

## What it does

1. **Discovers** every 9+1 event by scraping the race calendar and the volunteer
   page for cards tagged `9+1 Credit`, then following each "Learn More" link to
   its `events.nyrr.org` page. (No race names to maintain — it's all automatic.)
2. **Checks** each event page for open options. An option counts as open when it
   has a live `register.nyrr.org` link (filled ones show "Sold Out" / "All Spots
   Filled" and have none).
3. **Emails** you once when something opens. It won't re-nag while a spot stays
   open, and it re-arms if a spot closes and later reopens.

## Setup (about 10 minutes)

1. **Create a GitHub repo** and add these files. A **public** repo gets unlimited
   free Actions minutes (credentials live in Secrets, never in code, so public is
   safe).
2. **Gmail app password:** turn on 2-Step Verification on your Google account,
   then create an App Password (Google Account → Security → App passwords). It's a
   16-character code.
3. **Add repo Secrets** (Settings → Secrets and variables → Actions → New secret):
   | Secret | Value |
   |---|---|
   | `GMAIL_ADDRESS` | the Gmail you send from |
   | `GMAIL_APP_PASSWORD` | the 16-char app password (no spaces) |
   | `RECIPIENT_EMAIL` | where alerts go (can be the same address) |
4. **Listing URLs are pre-filled** in `config.yaml` (race calendar + volunteer
   page). If registration discovery ever logs "0 cards," re-check
   `listings.registration`.
5. **Test it:** in the Actions tab, open **NYRR check** → **Run workflow**. The
   first run sends a "watcher started" summary email. You're live.

## Local testing

```bash
pip install -r requirements.txt
python -m watcher.main --list      # dry run: prints discovered events + open options, no email
python -m watcher.main --refresh   # force re-scrape of the listing pages
```

To test email locally, set the env vars first:
```bash
export GMAIL_ADDRESS=you@gmail.com GMAIL_APP_PASSWORD=xxxx RECIPIENT_EMAIL=you@gmail.com
python -m watcher.main
```

Run the tests (no network needed):
```bash
python tests/test_parsing.py
python tests/test_lifecycle.py
```

## Timing & reliability

- GitHub cron is UTC and can lag 10–30 min under load, so "every 30 min" is
  approximate — fine for catching openings, and the email links straight to
  registration so you can act fast.
- The workflow won't tell you if it silently fails, so the watcher emails you on
  errors (and on an empty discovery), plus a weekly heartbeat that also keeps the
  repo active (GitHub disables schedules after 60 days of no repo activity).

## A note on access (please read)

The listing pages on **`www.nyrr.org`** and the checkout on **`register.nyrr.org`**
are marked disallowed in NYRR's `robots.txt`; the **`events.nyrr.org`** pages this
tool polls are not. `robots.txt` is an advisory standard, and a gentle personal
monitor of pages you can view yourself is a gray area — but it's worth reading
NYRR's Terms of Use and deciding for yourself before running it unattended.

To stay respectful, the design already:
- polls only `events.nyrr.org` on the frequent loop,
- scrapes the `www.nyrr.org` listings only every ~12 hours (`discovery_refresh_hours`)
  just to find event URLs,
- sends a real User-Agent and pauses between requests.

If you'd rather never touch `www.nyrr.org`, set `include_registration`/`include_volunteer`
and paste specific `events.nyrr.org` URLs — or ask for a "manual seed" mode.

## Config quick reference

See `config.yaml`. Common tweaks: `require_tags`, `only_names` / `exclude_names`,
`discovery_refresh_hours`, `quiet_hours`.

## Cost

$0 — public-repo Actions minutes and Gmail are both free.
