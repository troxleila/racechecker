"""Test the Haku widget API JSON parsing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from watcher.config import Config
from watcher.fetcher import _parse_haku_events


def _cfg(**over):
    base = dict(
        seed_events=[], require_tags=["9+1 Credit"], include_registration=True,
        include_volunteer=True, only_names=[], exclude_names=[],
        listing_registration="", listing_volunteer="", discovery_refresh_hours=12,
        recipient_email="x@y.com", user_agent="t", request_delay_seconds=0,
        quiet_hours=None, gmail_address=None, gmail_app_password=None,
    )
    base.update(over)
    return Config(**base)


# Simulated Haku API response — we don't know the exact shape yet, so test
# several plausible formats the parser handles.

def test_list_of_dicts():
    """Events as a flat list (most likely shape)."""
    data = [
        {"name": "NYRR Queens 10K", "tags": ["Scored", "9+1 Credit"],
         "slug": "nyrr-queens-10k"},
        {"name": "Fun Run", "tags": ["Scored"],
         "slug": "fun-run"},
        {"name": "Frosty 5K", "tags": [{"name": "9+1 Credit"}, {"name": "Scored"}],
         "url": "https://events.nyrr.org/nyrr-frosty-5k"},
    ]
    cfg = _cfg()
    events = _parse_haku_events(data, "registration", cfg)
    names = [e.name for e in events]
    assert "NYRR Queens 10K" in names
    assert "Fun Run" not in names  # no 9+1 tag
    assert "Frosty 5K" in names
    assert events[0].event_url == "https://events.nyrr.org/nyrr-queens-10k"
    assert events[1].event_url == "https://events.nyrr.org/nyrr-frosty-5k"
    print("✓ flat list parsed:", names)


def test_wrapped_in_dict():
    """Events nested under a key like {"events": [...]}."""
    data = {"events": [
        {"name": "Staten Island Half", "tags": ["9+1 Credit"], "slug": "si-half"},
    ]}
    events = _parse_haku_events(data, "volunteer", _cfg())
    assert len(events) == 1
    assert events[0].kind == "volunteer"
    print("✓ wrapped dict parsed:", events[0].name)


def test_tags_as_csv_string():
    """Tags as a comma-separated string."""
    data = [{"name": "Race X", "tags": "Scored, 9+1 Credit", "slug": "race-x"}]
    events = _parse_haku_events(data, "registration", _cfg())
    assert len(events) == 1
    print("✓ CSV tags parsed")


def test_exclude_filter():
    data = [{"name": "TCS NYC Marathon", "tags": ["9+1 Credit"], "slug": "marathon"}]
    cfg = _cfg(exclude_names=["Marathon"])
    events = _parse_haku_events(data, "registration", cfg)
    assert events == []
    print("✓ exclude_names filters Haku events")


def test_only_names_filter():
    data = [
        {"name": "Queens 10K", "tags": ["9+1 Credit"], "slug": "q10k"},
        {"name": "Bronx 10M", "tags": ["9+1 Credit"], "slug": "b10m"},
    ]
    cfg = _cfg(only_names=["Queens"])
    events = _parse_haku_events(data, "registration", cfg)
    assert len(events) == 1 and events[0].name == "Queens 10K"
    print("✓ only_names filters Haku events")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"\nAll {len(fns)} Haku tests passed.")
