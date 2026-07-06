"""Load config.yaml and merge in secrets from the environment."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class SeedEvent:
    url: str
    kind: str  # "registration" | "volunteer"


@dataclass
class Config:
    seed_events: list[SeedEvent]
    require_tags: list[str]
    include_registration: bool
    include_volunteer: bool
    only_names: list[str]
    exclude_names: list[str]
    listing_registration: str
    listing_volunteer: str
    discovery_refresh_hours: float
    recipient_email: str
    user_agent: str
    request_delay_seconds: float
    quiet_hours: list[int] | None
    # secrets (from env / GitHub Secrets)
    gmail_address: str | None
    gmail_app_password: str | None

    @property
    def email_ready(self) -> bool:
        return bool(self.gmail_address and self.gmail_app_password and self.recipient_email)

    @property
    def use_seeds(self) -> bool:
        return len(self.seed_events) > 0


def load_config(path: str | Path = "config.yaml") -> Config:
    raw = yaml.safe_load(Path(path).read_text())
    sel = raw.get("selection", {})
    listings = raw.get("listings", {})

    recipient = os.environ.get("RECIPIENT_EMAIL") or raw.get("recipient_email", "")

    seeds = []
    for entry in raw.get("seed_events") or []:
        if entry.get("url"):
            seeds.append(SeedEvent(url=entry["url"], kind=entry.get("kind", "registration")))

    return Config(
        seed_events=seeds,
        require_tags=sel.get("require_tags", []),
        include_registration=sel.get("include_registration", True),
        include_volunteer=sel.get("include_volunteer", True),
        only_names=sel.get("only_names", []),
        exclude_names=sel.get("exclude_names", []),
        listing_registration=listings.get("registration", ""),
        listing_volunteer=listings.get("volunteer", ""),
        discovery_refresh_hours=float(raw.get("discovery_refresh_hours", 12)),
        recipient_email=recipient,
        user_agent=raw.get("user_agent", "nyrr-watcher/1.0"),
        request_delay_seconds=float(raw.get("request_delay_seconds", 1.0)),
        quiet_hours=raw.get("quiet_hours"),
        gmail_address=os.environ.get("GMAIL_ADDRESS"),
        gmail_app_password=os.environ.get("GMAIL_APP_PASSWORD"),
    )
