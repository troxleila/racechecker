"""
Fetching + parsing.

Two layers:
  1. Discovery  — scrape a listing page (race calendar / volunteer page) for the
                  .upcoming-race-details cards, filter by tag, collect event URLs.
  2. Status     — fetch each events.nyrr.org page and find OPEN options.

Confirmed signal (verified live on events.nyrr.org):
  An option is OPEN if and only if it has a link to
      register.nyrr.org/?event=<EVENT_ID>&option=<OPTION_ID>
  Filled options show "Sold Out" / "All Spots Filled" and have no such link.
This link-presence test is used as the primary detector because it is structural
and does not depend on exact CSS class names or status wording.
"""
from __future__ import annotations

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


def make_session(cfg: Config) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": cfg.user_agent, "Accept-Language": "en-US,en;q=0.9"})
    return s


def fetch_html(url: str, session: requests.Session, timeout: int = 30) -> str:
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


# ── Discovery ────────────────────────────────────────────────────────────────

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

        # The "Learn More" link lives in the sibling .upcoming-race-aux that
        # follows this card in document order.
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
        except Exception as exc:  # noqa: BLE001 — one bad listing shouldn't kill the run
            print(f"[discover] WARNING: {kind} listing failed: {exc}")

    # De-duplicate by event_url + kind.
    seen = set()
    unique = []
    for e in found:
        k = (e.kind, e.event_url)
        if k not in seen:
            seen.add(k)
            unique.append(e)
    return unique


# ── Status ───────────────────────────────────────────────────────────────────

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
        # Drop the anchor's own text and known status/tag noise; keep the rest.
        parts = [p.strip() for p in re.split(r"\s{2,}|\n", node.get_text("\n", strip=True).replace("\r", ""))]
        cleaned = [p for p in parts if p and p.lower() not in _NOISE]
        if cleaned:
            # The role/option name is usually the longest non-noise fragment.
            return max(cleaned, key=len)[:120]
    return "registration option"


def parse_event_page(html: str, event_url: str, kind: str) -> tuple[str, list[Opening]]:
    """Return (event_name, [open options]) for one events.nyrr.org page."""
    soup = BeautifulSoup(html, "html.parser")

    # Event display name: <h1>, else <title>.
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
            continue  # a generic register link without a specific option
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
