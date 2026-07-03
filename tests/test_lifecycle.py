"""Simulate several polling cycles to verify alert dedupe / priming / re-arm."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from watcher import main as m           # noqa: E402
from watcher import notifier            # noqa: E402
from watcher.models import ListedEvent, Opening  # noqa: E402


def make_opening(oid, name="Test Race", eid="EVT1", kind="registration"):
    return Opening(event_id=eid, event_name=name, kind=kind, option_id=oid,
                   option_name=f"opt-{oid}", register_url=f"https://register.nyrr.org/?event={eid}&option={oid}",
                   event_url="https://events.nyrr.org/test")


CALLS = []
CURRENT = []  # openings returned by the mocked check_event this cycle


def _reset_calls():
    CALLS.clear()


def _patch(monkeypatch_cfg):
    m.get_events = lambda cfg, session, force: [ListedEvent("Test Race", ["9+1 Credit"],
                                                            "https://events.nyrr.org/test", "registration")]
    m.check_event = lambda ev, session, cfg: list(CURRENT)
    m.make_session = lambda cfg: None
    notifier.notify_init = lambda cfg, ops: CALLS.append(("init", [o.option_id for o in ops]))
    notifier.notify_openings = lambda cfg, ops: CALLS.append(("open", [o.option_id for o in ops]))
    notifier.notify_error = lambda cfg, msg: CALLS.append(("error", msg))


def run_cycle(cfg):
    _reset_calls()
    m.run(cfg, dry_run=False, force_refresh=False)
    return list(CALLS)


def main():
    tmp = tempfile.mkdtemp()
    os.chdir(tmp)
    Path("config.yaml").write_text("recipient_email: x@y.com\n")
    cfg = m.load_config("config.yaml")
    _patch(cfg)

    global CURRENT

    # Cycle 1: first run, two options open -> single init email, no per-open spam.
    CURRENT = [make_opening("A"), make_opening("B")]
    c = run_cycle(cfg)
    assert c == [("init", ["A", "B"])], c
    print("✓ cycle 1 (first run): init summary only ->", c)

    # Cycle 2: same two open -> no email.
    c = run_cycle(cfg)
    assert c == [], c
    print("✓ cycle 2 (unchanged): no email")

    # Cycle 3: a new option C opens -> alert for C only.
    CURRENT = [make_opening("A"), make_opening("B"), make_opening("C")]
    c = run_cycle(cfg)
    assert c == [("open", ["C"])], c
    print("✓ cycle 3 (new opening): alerts C only ->", c)

    # Cycle 4: C fills again (disappears) -> no email, but C is re-armed.
    CURRENT = [make_opening("A"), make_opening("B")]
    c = run_cycle(cfg)
    assert c == [], c
    print("✓ cycle 4 (C closed): no email, re-armed")

    # Cycle 5: C reopens -> alerts again.
    CURRENT = [make_opening("A"), make_opening("B"), make_opening("C")]
    c = run_cycle(cfg)
    assert c == [("open", ["C"])], c
    print("✓ cycle 5 (C reopened): alerts C again ->", c)

    print("\nAlert-lifecycle integration test passed.")


if __name__ == "__main__":
    main()
