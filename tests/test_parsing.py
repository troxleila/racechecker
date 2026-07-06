"""Offline tests for the parsing + selection logic (no network needed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from watcher.config import Config          # noqa: E402
from watcher.fetcher import (                # noqa: E402
    parse_listing, parse_event_page, _matches_selection,
)

# ── Real sample markup provided from the live NYRR listing pages ──────────────

RACE_LISTING = """
<div class="race-item">
  <div class="upcoming-race-details">
    <div class="upcoming-race-details-main">
      <h3 class="upcoming-race-title">NYRR Frosty 5K</h3>
      <p class="upcoming-race-location">Brooklyn</p>
      <p class="upcoming-race-sub-type">5K</p>
      <p class="upcoming-race-pricing">$37.01</p>
      <p class="upcoming-race-tags">
        <span class="upcoming-race-tag">Scored</span>
        <span class="upcoming-race-tag">9+1 Credit</span>
        <span class="upcoming-race-tag">Team for Kids</span>
      </p>
    </div>
  </div>
  <div class="upcoming-race-aux">
    <a target="_blank" href="https://events.nyrr.org/nyrr-frosty-5k" class="learn-more-btn">Learn More</a>
  </div>
</div>
<div class="race-item">
  <div class="upcoming-race-details">
    <div class="upcoming-race-details-main">
      <h3 class="upcoming-race-title">Some Non-Credit Fun Run</h3>
      <p class="upcoming-race-tags">
        <span class="upcoming-race-tag">Scored</span>
      </p>
    </div>
  </div>
  <div class="upcoming-race-aux">
    <a href="https://events.nyrr.org/some-fun-run" class="learn-more-btn">Learn More</a>
  </div>
</div>
"""

VOLUNTEER_LISTING = """
<div class="upcoming-race-details">
  <div class="upcoming-race-details-main">
    <h3 class="upcoming-race-title">9/11 Memorial &amp; Museum 4M - Volunteers</h3>
    <p class="upcoming-race-location">New York</p>
    <p class="upcoming-race-sub-type">Race</p>
    <p class="upcoming-race-tags">
      <span class="upcoming-race-tag">9+1 Credit</span>
    </p>
  </div>
</div>
<div class="upcoming-race-aux">
  <a target="_blank" href="https://events.nyrr.org/nyrr-retro-4-miler-volunteers" class="learn-more-btn">Learn More</a>
</div>
"""

# Volunteer event page: one AVAILABLE role (has Register link), rest filled.
EVENT_PAGE = """
<html><head><title>NYRR Volunteer</title></head><body>
<h1>9/11 Memorial &amp; Museum 4M - Volunteers</h1>
<ul>
  <li>Available
      Volunteer Leaders and Leaders in Training (NO +1)
      No +1
      <a href="https://register.nyrr.org/?event=3795532a07f238d3400e&option=ad7fd857c5981fe2002c">Register</a>
  </li>
  <li>All Spots Filled Bag Check 9+1</li>
  <li>All Spots Filled Course Marshal North 9+1</li>
  <li>Medical Available
      Medical Volunteers (Must be licensed in NYS)
      medical 9+1
      <a href="https://register.nyrr.org/?event=3795532a07f238d3400e&option=5d149a33bbc28aa0ee0f">Register</a>
  </li>
</ul>
</body></html>
"""

EVENT_PAGE_FILLED = """
<html><head><title>NYRR Volunteer</title></head><body>
<h1>Sold Out Race - Volunteers</h1>
<ul>
  <li>All Spots Filled Bag Check 9+1</li>
  <li>All Spots Filled Start and Finish 9+1</li>
</ul>
</body></html>
"""


def _cfg(**over):
    base = dict(
        seed_events=[], require_tags=["9+1 Credit"], include_registration=True, include_volunteer=True,
        only_names=[], exclude_names=[], listing_registration="", listing_volunteer="",
        discovery_refresh_hours=12, recipient_email="x@y.com", user_agent="t",
        request_delay_seconds=0, quiet_hours=None, gmail_address=None, gmail_app_password=None,
    )
    base.update(over)
    return Config(**base)


def test_parse_race_listing():
    events = parse_listing(RACE_LISTING, "registration")
    assert len(events) == 2, events
    frosty = events[0]
    assert frosty.name == "NYRR Frosty 5K"
    assert "9+1 Credit" in frosty.tags
    assert frosty.event_url == "https://events.nyrr.org/nyrr-frosty-5k"
    print("✓ race listing parsed:", frosty.name, frosty.tags)


def test_parse_volunteer_listing():
    events = parse_listing(VOLUNTEER_LISTING, "volunteer")
    assert len(events) == 1
    v = events[0]
    assert v.name == "9/11 Memorial & Museum 4M - Volunteers"
    assert v.event_url == "https://events.nyrr.org/nyrr-retro-4-miler-volunteers"
    assert v.kind == "volunteer"
    print("✓ volunteer listing parsed:", v.name)


def test_tag_filter():
    cfg = _cfg()
    events = parse_listing(RACE_LISTING, "registration")
    kept = [e for e in events if _matches_selection(e, cfg)]
    assert len(kept) == 1  # only the 9+1 Credit one survives
    assert kept[0].name == "NYRR Frosty 5K"
    print("✓ tag filter keeps only 9+1:", [e.name for e in kept])


def test_exclude_names():
    cfg = _cfg(exclude_names=["Frosty"])
    events = parse_listing(RACE_LISTING, "registration")
    kept = [e for e in events if _matches_selection(e, cfg)]
    assert kept == []
    print("✓ exclude_names works")


def test_event_page_open_options():
    name, openings = parse_event_page(EVENT_PAGE, "https://events.nyrr.org/x", "volunteer")
    assert name == "9/11 Memorial & Museum 4M - Volunteers"
    assert len(openings) == 2, openings
    ids = {o.option_id for o in openings}
    assert ids == {"ad7fd857c5981fe2002c", "5d149a33bbc28aa0ee0f"}
    assert all(o.event_id == "3795532a07f238d3400e" for o in openings)
    labels = {o.option_name for o in openings}
    print("✓ event page open options:", labels)


def test_event_page_filled():
    name, openings = parse_event_page(EVENT_PAGE_FILLED, "https://events.nyrr.org/y", "volunteer")
    assert openings == [], openings
    print("✓ fully-filled event yields no openings")


def test_opening_key_stability():
    _, openings = parse_event_page(EVENT_PAGE, "https://events.nyrr.org/x", "volunteer")
    keys = [o.key for o in openings]
    assert all(k.startswith("volunteer:3795532a07f238d3400e:") for k in keys)
    print("✓ opening keys:", keys)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"\nAll {len(fns)} tests passed.")
