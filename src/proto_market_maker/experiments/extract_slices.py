"""Build and run the per-day extraction request for one MM window.

This does not query market tables itself. It

1. reads ``quote.futurecontractcode`` (VN30F1M/VN30F2M -> dated contract per
   day) through the RIVF'26 extraction tool's own read-only client (DB) or its
   archive client, so credentials stay inside that tool and are never seen here;
2. picks the window's sessions and the contract the signal trades each day
   (:mod:`proto_market_maker.experiments.windows`);
3. writes a hand-written, per-day ``request.json`` naming exactly the
   (file, dated contract, day) triples the two arms read, and replays it with
   ``rivf26_extract.py declared --request`` into
   ``<workspace>/rivf26/data/mm-<window>-{tick,daily}/``;
4. copies the slice into this repo's ``data/`` with the tick/book tables cut to
   trading hours (08:45 <= t < 14:46, which drops the end-of-day ``00:00:00``
   row), and writes ``data/<window>-MANIFEST.md`` with sizes and sha256.

What each arm reads, and therefore what is requested:

=========================  ==============================  =================
file                        contract / days                 read by
=========================  ==============================  =================
local_quote_{bid,ask}price  contracts A touches (below)     faithful (book),
local_quote_{bid,ask}size   depth 1-3                       naive (depth 1)
local_quote_matched         F1M and F2M, every session      both
local_quote_total           contracts A touches (below)     faithful (tape)
quote_close                 F1M and F2M, every session      naive (+ marks)
quote_{ceil,floor,ref.}     F1M and F2M, every session      faithful (band)
quote_ticker                F1M and F2M contracts           DataHubSource root check
futurecontractcode (CSV)    the window                      both (contract map)
=========================  ==============================  =================

The bands cover **both** continuous contracts on every session, not only the
traded one: faithful-A (``mm_faithful_a``) carries inventory, so on a roll day
it closes F1 and opens F2, and the day after a roll it holds the contract it
rolled into while quoting the expiring F1 (naive's rule). Any contract A holds
or trades on a day must have that day's band, or the engine refuses its orders
(``BAND_LIMIT``, ``band_source: absent``). The rows are daily and tiny.

Book and sized tape follow the same principle (:func:`touched`): the traded
contract every session, plus both contracts on a roll day and the contract A
rolled into on the session after it. Without F1's sized tape on a roll day the
conservative taker walk of A's F1 close leg is INDETERMINATE and never fills.

Run (from the repo root)::

    .venv/bin/python -m proto_market_maker.experiments.extract_slices krx2025
    .venv/bin/python -m proto_market_maker.experiments.extract_slices im2022
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import date, time, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from proto_market_maker.experiments.windows import (WINDOWS, roll_days,
                                                     select_sessions,
                                                     traded_contracts)

REPO = Path(__file__).resolve().parents[3]
#: The workspace layout: <ws>/proto/ProtoMarketMaker, <ws>/plutus-simulator,
#: <ws>/rivf26/data. Override with PLUTUS_SIM_ROOT / MM_SLICE_ROOT.
SIM_ROOT = Path(os.environ.get("PLUTUS_SIM_ROOT", REPO.parents[1] / "plutus-simulator"))
TOOL = SIM_ROOT / "scripts" / "rivf26_extract.py"
TOOL_PY = SIM_ROOT / ".venv" / "bin" / "python"
OUT_ROOT = Path(os.environ.get("MM_SLICE_ROOT", REPO.parents[1] / "rivf26" / "data"))

SESSION_FROM = time(8, 45)
SESSION_TO = time(14, 46)
BOOK = ("local_quote_bidprice", "local_quote_askprice",
        "local_quote_bidsize", "local_quote_asksize")
TICK = BOOK + ("local_quote_matched", "local_quote_total")
#: Same writer settings as the tool, so the trimmed copy is deterministic too.
WRITER = dict(compression="zstd", compression_level=9, use_dictionary=True,
              write_statistics=True, version="2.6", data_page_version="1.0",
              row_group_size=1 << 20, store_schema=True)


def _client(source: str):
    sys.path.insert(0, str(TOOL.parent))
    import rivf26_extract as tool  # noqa: E402  (the coordinator's tool)
    return tool.ArchiveClient() if source == "archive" else tool.PgClient()


def _day(d) -> date:
    return d if type(d) is date else d.date()


def contract_map(lo: date, hi: date) -> Tuple[Dict[Tuple[date, str], str], set]:
    """(day, continuous code) -> dated contract, and the days that traded.

    Read from the DB (daily facts). ``futurecontractcode`` also carries rows on
    market holidays (e.g. 2025-04-07, 2025-04-30..05-02), so a session is a day
    on which the mapped VN30F1M contract has a ``quote.close`` row.
    """
    db = _client("db")
    try:
        rows = db.fetch(
            "SELECT datetime, tickersymbol, futurecode FROM quote.futurecontractcode "
            "WHERE datetime >= %s AND datetime < %s ORDER BY datetime", [lo, hi])
        out = {(_day(d), code): t for d, t, code in rows
               if code in ("VN30F1M", "VN30F2M")}
        f1 = sorted({t for (_, c), t in out.items() if c == "VN30F1M"})
        closes = db.fetch(
            "SELECT datetime, tickersymbol FROM quote.close WHERE "
            "tickersymbol = ANY(%s) AND datetime >= %s AND datetime < %s",
            [f1, lo, hi])
    finally:
        db.close()
    have = {(_day(d), t) for d, t in closes}
    traded = {d for (d, c), t in out.items() if c == "VN30F1M" and (d, t) in have}
    return out, traded


def _intervals(days: List[date]) -> List[List[str]]:
    """Per-day [d, d+1) intervals, merged when consecutive in the session list."""
    out: List[List[str]] = []
    for d in sorted(days):
        lo, hi = d.isoformat(), (d + timedelta(days=1)).isoformat()
        out.append([lo, hi])
    return out


def touched(i: int, sessions: List[date], fcc, traded, rolls) -> set:
    """Contracts A may hold or trade on ``sessions[i]``; F reads book and sized
    tape for each of them.

    * the traded contract (quoted all day);
    * on a roll day, **both** F1M and F2M: A closes F1 and opens F2 there;
    * the previous session's traded contract, if it still lists today: A
      carries inventory, so after a roll it holds the contract it rolled into
      while quoting the expiring F1 (naive's rule), and a roll leg left unfilled
      leaves F1 held into its expiry day. An engine forced close or a resubmitted
      leg on such a contract needs its book and tape.

    Restricted to the day's F1M/F2M (an expired contract no longer lists).
    """
    d = sessions[i]
    listed = {fcc[(d, "VN30F1M")], fcc[(d, "VN30F2M")]}
    out = {traded[d]}
    if d in rolls:
        out |= listed
    if i > 0:
        prev = sessions[i - 1]
        out.add(traded[prev])
        if prev in rolls:
            out |= {fcc[(prev, "VN30F1M")], fcc[(prev, "VN30F2M")]}
    return out & listed


def build_request(sessions: List[date], fcc) -> dict:
    traded = traded_contracts(sessions, fcc)
    rolls = set(roll_days(sessions))
    per: Dict[str, Dict[str, List[date]]] = {}

    def add(file, ticker, d):
        per.setdefault(file, {}).setdefault(ticker, []).append(d)

    for i, d in enumerate(sessions):
        f1, f2, t = fcc[(d, "VN30F1M")], fcc[(d, "VN30F2M")], traded[d]
        for c in sorted(touched(i, sessions, fcc, traded, rolls)):
            for f in BOOK:
                add(f + ".parquet", c, d)
            add("local_quote_total.parquet", c, d)
        add("local_quote_matched.parquet", f1, d)
        add("local_quote_matched.parquet", f2, d)
        add("quote_close.parquet", f1, d)
        add("quote_close.parquet", f2, d)
        for f in ("quote_ceil", "quote_floor", "quote_reference"):
            add(f + ".parquet", f1, d)      # both contracts: see the module doc
            add(f + ".parquet", f2, d)
    files = []
    for file in sorted(per):
        entry = {"file": file,
                 "tickers": {t: _intervals(ds) for t, ds in sorted(per[file].items())}}
        if file.replace(".parquet", "") in BOOK:
            entry["depth"] = [1, 3]
        files.append(entry)
    # The ticker master must exist for DataHubSource to open the root (futures
    # are typed by code prefix, so its rows are not otherwise read).
    held = {fcc[(d, c)] for d in sessions for c in ("VN30F1M", "VN30F2M")}
    files.append({"file": "quote_ticker.parquet",
                  "tickers": {t: None for t in sorted(held)}})
    files.sort(key=lambda e: e["file"])
    return {"version": 1, "files": files}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def trim_copy(src: Path, dst: Path) -> Tuple[int, int]:
    table = pq.read_table(src)
    before = table.num_rows
    if src.stem in TICK:
        t = pc.cast(table["datetime"], pa.time64("us")) if False else None
        secs = pc.add(pc.multiply(pc.hour(table["datetime"]), 3600),
                      pc.multiply(pc.minute(table["datetime"]), 60))
        lo = SESSION_FROM.hour * 3600 + SESSION_FROM.minute * 60
        hi = SESSION_TO.hour * 3600 + SESSION_TO.minute * 60
        mask = pc.and_(pc.greater_equal(secs, lo), pc.less(secs, hi))
        table = table.filter(mask)
    dst.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, dst, **WRITER)
    return before, table.num_rows


WHY = {
    "krx2025": (
        "20 sessions either side of the 2025-05-05 KRX cutover, the low end of the "
        "handoff's 20-30: enough for the regime guard to act on every post-cutover "
        "session and for both arms to quote a non-trivial number of times on each "
        "side. MM has no look-back, so no warm-up. Only the contract the signal "
        "trades each day carries book and tape; VN30F2M otherwise contributes "
        "matched prices, closes and daily bands (bands for both contracts on every "
        "session, so a roll can close F1 and open F2). Depth "
        "1-3 is all the DB holds and all the book walk reads."),
    "im2022": (
        "20 sessions either side of the 2022-12-15 VSD IM step 13% -> 17%, so one "
        "deposit is margined at both ratios inside one run. Book sizes from the "
        "archive (the DB has none before 2023-01-03); daily bands from the DB. Same "
        "per-day contract rule and fields as krx2025. ceil/floor are missing (DB and "
        "archive) for VN30F2212 on 2022-12-02, 12-05, 12-06 and for VN30F2301 on "
        "2022-12-01..12-06 (reference is present): a data gap, not filled. Bands "
        "cover both VN30F1M and VN30F2M on every session, so every roll day carries "
        "both contracts' bands."),
}
SIZE_NOTE = (
    "Over 3 MiB: L2 depth 1-3 with sizes plus the sized tape is what the queue "
    "claims read; 40 sessions is the handoff's floor, so this is irreducible "
    "without shortening the window. The growth over the first extraction "
    "(+0.11 MiB im2022, +0.52 MiB krx2025) comes only from the roll days and the "
    "session after each roll, where book and sized tape now cover both contracts A "
    "holds or trades (see ``touched``); bands grew by the F2M rows.")


def why_section(name: str) -> List[str]:
    return ["## Why this window is minimal", "", WHY[name], "",
            "## Size flag", "", SIZE_NOTE, ""]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("window", choices=sorted(WINDOWS))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--parts", default="tick,daily",
                    help="which slices to (re-)extract; the manifest always covers both")
    args = ap.parse_args(argv)
    todo = set(args.parts.split(","))
    w = WINDOWS[args.window]
    fcc, traded_days = contract_map(w.pivot - timedelta(days=60),
                                    w.pivot + timedelta(days=60))
    sessions = select_sessions(sorted(traded_days), w)
    request = build_request(sessions, fcc)

    # Book/tape from the window's source; daily bands always from the DB (the
    # archive lacks ceil/floor on some days, e.g. VN30F2212 2022-12-02..06).
    parts = {"tick": ("local_quote", w.source), "daily": ("quote_", "db")}
    slice_dirs = []
    for part, (prefix, source) in parts.items():
        if part not in todo:
            slice_dirs.append(OUT_ROOT / f"mm-{w.name}-{part}")
            continue
        sub = {"version": 1, "files": [f for f in request["files"]
                                       if f["file"].startswith(prefix)]}
        experiment = f"mm-{w.name}-{part}"
        work = OUT_ROOT / f"{experiment}-request.json"
        work.write_text(json.dumps(sub, indent=1, sort_keys=True) + "\n")
        cmd = [str(TOOL_PY), str(TOOL), "declared", "--source", source,
               "--experiment", experiment, "--request", str(work),
               "--reproduces", f"ProtoMarketMaker mm_anchor window {w.name}: {w.note}"]
        if args.force:
            cmd.append("--force")
        subprocess.run(cmd, check=True)
        work.unlink()
        slice_dirs.append(OUT_ROOT / experiment)

    slice_dir = slice_dirs[0]
    # the contract map the runner reads (written beside the tool's slice too)
    rows = sorted((d.isoformat(), c, t) for (d, c), t in fcc.items()
                  if d in set(sessions))
    for target in (slice_dir / "futurecontractcode.csv",
                   REPO / "data" / "market" / w.name / "futurecontractcode.csv"):
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", newline="", encoding="utf-8") as fh:
            wr = csv.writer(fh, lineterminator="\n")
            wr.writerow(["datetime", "futurecode", "tickersymbol"])
            wr.writerows(rows)

    lines = [f"# Data manifest: ProtoMarketMaker window `{w.name}`", "",
             f"- Window: {sessions[0]} .. {sessions[-1]} ({len(sessions)} sessions; "
             f"{w.sessions_before} before and {w.sessions_after} from {w.pivot}: {w.note})",
             f"- Source: book/tape `{w.source}`, daily bands `db`, via "
             f"`plutus-simulator/scripts/rivf26_extract.py declared --request` (slices "
             f"`rivf26/data/mm-{w.name}-tick/` and `mm-{w.name}-daily/`; their "
             f"DATA-MANIFEST.md and request.json carry the untrimmed sha256s)",
             f"- Trimmed here to trading hours {SESSION_FROM}..{SESSION_TO} for tick/book "
             "tables (drops the end-of-day 00:00:00 row); daily tables copied unchanged.",
             "- Prices are VN30F index points (1 point = 100,000 dong per contract).",
             "", "| file | rows (slice -> repo) | bytes | sha256 |", "|---|--:|--:|---|"]
    total = 0
    for src in sorted(p for d in slice_dirs for p in d.glob("*.parquet")):
        sub = "l2" if src.stem.startswith("local_quote") else "band"
        dst = REPO / "data" / sub / w.name / src.name
        before, after = trim_copy(src, dst)
        size = dst.stat().st_size
        total += size
        lines.append(f"| data/{sub}/{w.name}/{src.name} | {before} -> {after} | {size} | `{sha256(dst)}` |")
    fc = REPO / "data" / "market" / w.name / "futurecontractcode.csv"
    total += fc.stat().st_size
    lines.append(f"| data/market/{w.name}/futurecontractcode.csv | {len(rows)} | {fc.stat().st_size} | `{sha256(fc)}` |")
    lines += ["", f"Total: {total} bytes ({total / 2**20:.2f} MiB).", ""]
    lines += why_section(w.name)
    (REPO / "data" / f"{w.name}-MANIFEST.md").write_text("\n".join(lines))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
