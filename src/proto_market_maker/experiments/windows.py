"""The two experiment windows and the per-day contract the signal trades.

Shared by the extractor (which must know which dated contract to pull on which
day) and the runner (which must trade exactly that contract), so the two can
never disagree.

Windows (handoff T5):

* ``krx2025`` (primary): 20 sessions either side of the 2025-05-05 KRX
  cutover. Book sizes come from the Algotrade DB (sizes exist from 2023-01-03).
* ``im2022`` (robustness): 20 sessions either side of the 2022-12-15 VSD
  initial-margin step 13% -> 17%. Book sizes come from the local parquet
  archive (sizes exist from 2021-07-01; the DB has none before 2023).

The contract rule is the naive engine's own (``backtest.Backtesting.run``):
trade the VN30F1M dated contract, except on the session whose *next* session
falls on or after the front month's expiry (third Thursday), when the engine
moves to VN30F2M for that session. ``futurecontractcode`` maps the continuous
codes to the dated contract per day.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Sequence, Tuple

from dateutil.rrule import rrule, MONTHLY, TH


@dataclass(frozen=True)
class Window:
    name: str
    pivot: date               # the dated rule change the window straddles
    sessions_before: int
    sessions_after: int       # including the pivot session
    source: str               # extraction source: 'db' or 'archive'
    note: str


WINDOWS: Dict[str, Window] = {
    "krx2025": Window("krx2025", date(2025, 5, 5), 20, 20, "db",
                      "KRX matching/margin cutover 2025-05-05 (primary)"),
    "im2022": Window("im2022", date(2022, 12, 15), 20, 20, "archive",
                     "VSD initial margin 13% -> 17% on 2022-12-15 (robustness)"),
}


def select_sessions(all_days: Sequence[date], window: Window) -> List[date]:
    days = sorted(set(all_days))
    before = [d for d in days if d < window.pivot][-window.sessions_before:]
    after = [d for d in days if d >= window.pivot][:window.sessions_after]
    if len(before) < window.sessions_before or len(after) < window.sessions_after:
        raise ValueError(f"not enough sessions around {window.pivot}")
    return before + after


def expiries(start: date, end: date) -> List[date]:
    return [d.date() for d in rrule(freq=MONTHLY, byweekday=TH(3),
                                    dtstart=datetime.combine(start, datetime.min.time()),
                                    until=datetime.combine(end, datetime.min.time()))]


def roll_days(sessions: Sequence[date]) -> List[date]:
    """Sessions on which the naive engine trades F2M (its ``moving_to_f2``)."""
    queue = expiries(sessions[0], sessions[-1])
    rolls = []
    for i, d in enumerate(sessions):
        if i != len(sessions) - 1 and queue and sessions[i + 1] >= queue[0]:
            rolls.append(d)
            queue.pop(0)
    return rolls


def traded_contracts(sessions: Sequence[date],
                     fcc: Dict[Tuple[date, str], str]) -> Dict[date, str]:
    """day -> dated contract the signal trades that day."""
    rolls = set(roll_days(sessions))
    return {d: fcc[(d, "VN30F2M" if d in rolls else "VN30F1M")] for d in sessions}
