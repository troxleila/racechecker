"""Small data structures shared across the watcher."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ListedEvent:
    """One card scraped from a listing page (race calendar or volunteer page)."""
    name: str
    tags: list[str]
    event_url: str          # link to the events.nyrr.org page
    kind: str               # "registration" | "volunteer"


@dataclass
class Opening:
    """One registration option / volunteer role that is currently OPEN."""
    event_id: str           # stable Haku id from the register link (event=...)
    event_name: str
    kind: str               # "registration" | "volunteer"
    option_id: str          # option=... from the register link
    option_name: str        # best-effort human label (e.g. "Bag Check")
    register_url: str       # direct link to act on
    event_url: str

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.event_id}:{self.option_id}"
