"""
Entry point. One cycle:
  discover (cached) -> check each event -> diff vs state -> email new opens -> save

CLI:
  python -m watcher.main            # normal run
  python -m watcher.main --list     # dry run: print everything, no email, no writes
  python -m watcher.main --refresh  # force re-scrape of listing pages
  python -m watcher.main --heartbeat# send weekly "still alive" email (+ touch state)
"""
from __future__ import annotations

import argparse
import sys
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import notifier, state
from .config import Config, load_config
from .fetcher import check_event, discover, make_session
from .models import ListedEvent, Opening

NY_TZ = ZoneInfo("America/New_York")


# ── discovery with cache ─────────────────────────────────────────────────────

def get_events(cfg: Config, session, force_refresh: bool) -> list[ListedEvent]:
    cache = state.load_cache()
    fresh_enough = (cache is not None
                    and not force_refresh
                    and state.cache_age_hours(cache) < cfg.discovery_refresh_hours)
    if fresh_enough:
        print(f"[discover] using cached list ({len(cache['events'])} events, "
              f"{state.cache_age_hours(cache):.1f}h old)")
        return [ListedEvent(**e) for e in cache["events"]]

    events = discover(cfg, session)
    if events:
        state.save_cache([asdict(e) for e in events])
    elif cache is not None:
        # Discovery came back empty but we have a prior list — reuse it rather
        # than go blind (listing pages occasionally hiccup).
        print("[discover] empty result; falling back to cached list")
        return [ListedEvent(**e) for e in cache["events"]]
    return events


# ── quiet hours ──────────────────────────────────────────────────────────────

def in_quiet_hours(cfg: Config) -> bool:
    if not cfg.quiet_hours:
        return False
    start, end = cfg.quiet_hours
    hour = datetime.now(NY_TZ).hour
    return (start <= hour or hour < end) if start > end else (start <= hour < end)


# ── core run ─────────────────────────────────────────────────────────────────

def run(cfg: Config, dry_run: bool, force_refresh: bool) -> int:
    session = make_session(cfg)
    events = get_events(cfg, session, force_refresh)

    if not events:
        raise RuntimeError(
            "No 9+1 events discovered from either listing page. The calendar URL "
            "may be wrong, the page structure changed, or access was blocked."
        )

    # Gather all currently-open options across watched events.
    current: dict[str, Opening] = {}
    for ev in events:
        try:
            for op in check_event(ev, session, cfg):
                current[op.key] = op
        except Exception as exc:  # noqa: BLE001
            print(f"[check] WARNING: {ev.name} ({ev.event_url}) failed: {exc}")

    print(f"[check] {len(events)} events watched, {len(current)} option(s) open now")

    if dry_run:
        for ev in events:
            print(f"  - [{ev.kind}] {ev.name} -> {ev.event_url}")
        print("\nCurrently OPEN:")
        for op in current.values():
            print(f"  * [{op.kind}] {op.event_name} — {op.option_name}\n    {op.register_url}")
        return 0

    st = state.load_state()
    first_run = not state.state_exists()
    now = datetime.now(timezone.utc).isoformat()

    new_opens: list[Opening] = []
    for key, op in current.items():
        prev = st.get(key)
        already = prev and prev.get("alerted_for") == "OPEN"
        if not already:
            new_opens.append(op)
        st[key] = {"alerted_for": "OPEN", "last_status": "OPEN", "last_seen": now,
                   "event_name": op.event_name, "option_name": op.option_name}

    # Re-arm: options that were open before but are gone now can alert again later.
    for key, rec in st.items():
        if key not in current and rec.get("alerted_for") == "OPEN":
            rec["alerted_for"] = None
            rec["last_status"] = "CLOSED"
            rec["last_seen"] = now

    quiet = in_quiet_hours(cfg)
    if first_run:
        notifier.notify_init(cfg, list(current.values()))
    elif new_opens and not quiet:
        notifier.notify_openings(cfg, new_opens)
    elif new_opens and quiet:
        # Don't mark as alerted during quiet hours; let them fire next run.
        print(f"[quiet] holding {len(new_opens)} alert(s) until quiet hours end")
        for op in new_opens:
            st[op.key]["alerted_for"] = None
    else:
        print("[run] no new openings")

    state.save_state(st)
    return 0


def heartbeat(cfg: Config) -> int:
    session = make_session(cfg)
    events = get_events(cfg, session, force_refresh=False)
    current = {}
    for ev in events:
        try:
            for op in check_event(ev, session, cfg):
                current[op.key] = op
        except Exception as exc:  # noqa: BLE001
            print(f"[heartbeat] WARNING: {ev.name} failed: {exc}")
    notifier.notify_heartbeat(cfg, len(events), len(current))
    # Touch state so the repo stays active (avoids GitHub's 60-day auto-disable).
    st = state.load_state()
    st["_heartbeat"] = {"last": datetime.now(timezone.utc).isoformat()}
    state.save_state(st)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="NYRR race/volunteer spot watcher")
    parser.add_argument("--list", action="store_true", help="dry run; print, don't email or write")
    parser.add_argument("--refresh", action="store_true", help="force re-scrape of listing pages")
    parser.add_argument("--heartbeat", action="store_true", help="send weekly check-in email")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)

    try:
        if args.heartbeat:
            return heartbeat(cfg)
        return run(cfg, dry_run=args.list, force_refresh=args.refresh)
    except Exception:  # noqa: BLE001
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        try:
            notifier.notify_error(cfg, tb)
        except Exception:  # noqa: BLE001
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
