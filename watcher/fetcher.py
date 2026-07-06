"""
Fetching + parsing.

Three discovery paths (tried in order):
  1. Haku widget API  — structured JSON from widget.hakuapp.com (preferred).
  2. Seed mode        — explicit events.nyrr.org URLs from config.yaml.
  3. Listing scrape   — parse .upcoming-race-details from listing pages (fallback).

Status check (for all paths):
  Fetch each events.nyrr.org page. An option is OPEN if and only if it has a
  link to register.nyrr.org/?event=<EVENT_ID>&option=<OPTION_ID>.
  Filled options show "Sold Out" / "All Spots Filled" and have no such link.
"""
from __future__ import annotations

import json
import re
import time
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from .config import Config
from .models import ListedEvent, Opening

REGISTER_RE = re.compile(r"register\.nyrr\.org", re.I)

# Words we strip when trying to name a volunteer role / registration option.
_NOISE = {
    "register", "available", "medical available", "sold out", "all spots filled",
    "9+1", "9+1 credit", "no +1", "scored", "medical",
}

# ── Haku widget API ──────────────────────────────────────────────────────────

HAKU_RACE_URL = (
    "https://widget.hakuapp.com/v2/event_lists"
    "?api_key=ZUSQ2ZfFgH5ia2E38BEKS4VVkVwIL9Y9aCLhk043"
    "&widget_scope=Endurance"
)
HAKU_VOLUNTEER_URL = (
    "https://widget.hakuapp.com/v2/event_lists"
    "?api_key=ZUSQ2ZfFgH5ia2E38BEKS4VVkVwIL9Y9aCLhk043"
    "&widget_scope=Volunteer"
)
HAKU_REFERER = "https://www.nyrr.org/"
HAKU_ORIGIN = "https://www.nyrr.org"


def _haku_headers(cfg: Config) -> dict:
    return {
        "User-Agent": cfg.user_agent,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": HAKU_REFERER,
        "Origin": HAKU_ORIGIN,
    }


def _parse_haku_events(data: dict | list, kind: str, cfg: Config) -> list[ListedEvent]:
    """Parse Haku API JSON into ListedEvents, filtering by 9+1 tag."""
    events: list[ListedEvent] = []

    # The response shape may be a list of events directly, or nested under a key.
    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # Try common wrapper keys.
        for key in ("events", "data", "items", "event_lists", "results"):
            if key in data and isinstance(data[key], list):
                items = data[key]
                break
        if not items:
            # Maybe the dict itself contains event-like fields at top level,
            # or the entire response is a single wrapper — log it for debugging.
            print(f"[haku] unexpected JSON shape, keys: {list(data.keys())[:20]}")
            return events

    for item in items:
        if not isinstance(item, dict):
            continue

        # Extract name.
        name = (item.get("name") or item.get("title") or
                item.get("event_name") or item.get("display_name") or "")
        if not name:
            continue

        # Extract tags.
        raw_tags = item.get("tags") or item.get("labels") or []
        if isinstance(raw_tags, str):
            raw_tags = [t.strip() for t in raw_tags.split(",")]
        elif isinstance(raw_tags, list):
            raw_tags = [
                (t.get("name") or t.get("label") or str(t)) if isinstance(t, dict) else str(t)
                for t in raw_tags
            ]

        # 9+1 filter.
        tags_lower = [t.lower() for t in raw_tags]
        has_required = all(
            any(req.lower() in t for t in tags_lower)
            for req in cfg.require_tags
        )
        if not has_required:
            continue

        # Extract event URL.
        url = (item.get("url") or item.get("event_url") or
               item.get("registration_url") or item.get("link") or "")
        slug = item.get("slug") or item.get("event_slug") or ""
        if not url and slug:
            url = f"https://events.nyrr.org/{slug}"
        if not url:
            # Try to build from id.
            eid = item.get("id") or item.get("event_id") or ""
            if eid:
                url = f"https://events.nyrr.org/{eid}"
        if not url:
            continue

        # Apply name filters.
        name_lower = name.lower()
        if cfg.only_names and not any(n.lower() in name_lower for n in cfg.only_names):
            continue
        if any(n.lower() in name_lower for n in cfg.exclude_names):
            continue

        events.append(ListedEvent(name=name, tags=raw_tags, event_url=url, kind=kind))

    return events


def discover_haku(cfg: Config, session: requests.Session) -> list[ListedEvent]:
    """Try the Haku widget API for auto-discovery."""
    headers = _haku_headers(cfg)
    found: list[ListedEvent] = []

    targets = []
    if cfg.include_registration:
        targets.append(("registration", HAKU_RACE_URL))
    if cfg.include_volunteer:
        targets.append(("volunteer", HAKU_VOLUNTEER_URL))

    for kind, url in targets:
        try:
            resp = session.get(url, headers=headers, timeout=30)
            if resp.status_code == 403:
                print(f"[haku] {kind}: 403 Forbidden (Referer/Origin rejected)")
                return []  # signal that Haku path doesn't work
            resp.raise_for_status()
            data = resp.json()
            events = _parse_haku_events(data, kind, cfg)
            print(f"[haku] {kind}: {len(events)} 9+1 events found")
            found.extend(events)
        except (requests.RequestException, json.JSONDecodeError) as exc:
            print(f"[haku] {kind}: failed: {exc}")
            return []  # fall through to next discovery method

    return found


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_session(cfg: Config) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": cfg.user_agent, "Accept-Language": "en-US,en;q=0.9"})
    return s


def fetch_html(url: str, session: requests.Session, timeout: int = 30) -> str:
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


# ── Discovery (listing-page scrape — fallback) ──────────────────────────────

def parse_listing(html: str, kind: str) -> list[ListedEvent]:
    """Parse .upcoming-race-details cards from a listing page."""
    soup = BeautifulSoup(html, "html.parser")
    events: list[ListedEvent] = []

    for card in soup.select(".upcoming-race-details"):
        title_el = card.select_one(".upcoming-race-title")
        if not title_el:
            continue
        name = title_el.get_text(strip=True)
        tags = [t.get_text(strip=True) for t in card.select(".upcoming-race-tag")]

        link = card.find_next("a", class_="learn-more-btn")
        href = link.get("href", "").strip() if link else ""
        if not href:
            continue

        events.append(ListedEvent(name=name, tags=tags, event_url=href, kind=kind))

    return events


def _matches_selection(ev: ListedEvent, cfg: Config) -> bool:
    tags_lower = [t.lower() for t in ev.tags]
    for req in cfg.require_tags:
        if not any(req.lower() in t for t in tags_lower):
            return False
    name_lower = ev.name.lower()
    if cfg.only_names and not any(n.lower() in name_lower for n in cfg.only_names):
        return False
    if any(n.lower() in name_lower for n in cfg.exclude_names):
        return False
    return True


def discover(cfg: Config, session: requests.Session) -> list[ListedEvent]:
    """Scrape the configured listing pages and return matching events."""
    found: list[ListedEvent] = []
    targets = []
    if cfg.include_registration and cfg.listing_registration:
        targets.append(("registration", cfg.listing_registration))
    if cfg.include_volunteer and cfg.listing_volunteer:
        targets.append(("volunteer", cfg.listing_volunteer))

    for kind, url in targets:
        try:
            html = fetch_html(url, session)
            listed = parse_listing(html, kind)
            kept = [e for e in listed if _matches_selection(e, cfg)]
            print(f"[discover] {kind}: {len(listed)} cards, {len(kept)} match tags")
            found.extend(kept)
        except Exception as exc:
            print(f"[discover] WARNING: {kind} listing failed: {exc}")

    seen = set()
    unique = []
    for e in found:
        k = (e.kind, e.event_url)
        if k not in seen:
            seen.add(k)
            unique.append(e)
    return unique


# ── Status (event page check — used by all paths) ───────────────────────────

def _option_label(anchor) -> str:
    """Best-effort human label for the option this Register link belongs to."""
    node = anchor
    for _ in range(4):
        node = node.parent
        if node is None:
            break
        text = " ".join(node.get_text(" ", strip=True).split())
        if len(text) < 4:
            continue
        parts = [p.strip() for p in re.split(r"\s{2,}|\n", node.get_text("\n", strip=True).replace("\r", ""))]
        cleaned = [p for p in parts if p and p.lower() not in _NOISE]
        if cleaned:
            return max(cleaned, key=len)[:120]
    return "registration option"


def parse_event_page(html: str, event_url: str, kind: str) -> tuple[str, list[Opening]]:
    """Return (event_name, [open options]) for one events.nyrr.org page."""
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")
    title_tag = soup.find("title")
    event_name = (h1.get_text(strip=True) if h1
                  else title_tag.get_text(strip=True) if title_tag
                  else event_url)

    openings: list[Opening] = []
    seen_options: set[str] = set()

    for a in soup.find_all("a", href=REGISTER_RE):
        href = a.get("href", "")
        qs = parse_qs(urlparse(href).query)
        event_id = (qs.get("event") or [""])[0]
        option_id = (qs.get("option") or [""])[0]
        if not event_id or not option_id:
            continue
        if option_id in seen_options:
            continue
        seen_options.add(option_id)
        openings.append(Opening(
            event_id=event_id,
            event_name=event_name,
            kind=kind,
            option_id=option_id,
            option_name=_option_label(a),
            register_url=href,
            event_url=event_url,
        ))

    return event_name, openings


def check_event(ev: ListedEvent, session: requests.Session, cfg: Config) -> list[Opening]:
    html = fetch_html(ev.event_url, session)
    _, openings = parse_event_page(html, ev.event_url, ev.kind)
    if cfg.request_delay_seconds:
        time.sleep(cfg.request_delay_seconds)
    return openings
