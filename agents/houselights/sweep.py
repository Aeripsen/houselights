"""One snapshot of the whole 70mm engagement, written as JSONL for ClickHouse.

Per run: every bookable date at every watched house -> every session (all films, so the agent can
see what else the house is selling and how far ahead) -> for the seat-level houses, every seat of
every session of the watched film. Output: data/snapshots/<ts>.sessions.jsonl and .seats.jsonl.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


from . import cineplex as cpx

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def run(out_dir=ROOT / "data" / "snapshots", seat_level=True, log=print, theatres=None):
    ts = datetime.now(timezone.utc).replace(microsecond=0)
    stamp = ts.strftime("%Y%m%dT%H%M%SZ")
    out_dir.mkdir(parents=True, exist_ok=True)
    sess_path = out_dir / (stamp + ".sessions.jsonl")
    seat_path = out_dir / (stamp + ".seats.jsonl")
    film_id = CONFIG["film_id"]
    n_sess = n_seat = 0
    houses = {k: v for k, v in CONFIG["theatres"].items() if not theatres or k in theatres}
    with sess_path.open("w", encoding="utf-8") as fs, seat_path.open("w", encoding="utf-8") as fq:
        for tid, name in houses.items():
            dates = cpx.bookable_dates(tid, film_id)
            log(f"{name}: {len(dates)} bookable dates")
            for day in dates:
                for s in cpx.showtimes(tid, day):
                    s["snapshot_ts"] = ts.isoformat()
                    s["theatre_name"] = name
                    fs.write(json.dumps(s) + "\n")
                    n_sess += 1
                    if not (seat_level and tid in CONFIG["seat_level_theatres"]
                            and s["film_id"] == film_id):
                        continue
                    rows = cpx.seat_layout(tid, s["session_id"], s["auditorium"])
                    avail = cpx.seat_availability(tid, s["session_id"])
                    if not rows or avail is None:
                        continue
                    for r in rows:
                        for seat in r["seats"]:
                            fq.write(json.dumps({
                                "snapshot_ts": ts.isoformat(), "theatre_id": tid,
                                "theatre_name": name, "session_id": s["session_id"],
                                "session_start": s["start"], "row": r["label"],
                                "seat": seat["label"], "seat_id": seat["id"],
                                "col": seat["column"], "seat_type": seat["type"],
                                "status": avail.get(seat["id"], "Unknown"),
                            }) + "\n")
                            n_seat += 1
                log(f"  {name} {day}: sessions so far {n_sess}, seats {n_seat}")
    log(f"done {stamp}: {n_sess} sessions, {n_seat} seats")
    return sess_path, seat_path


if __name__ == "__main__":
    t0 = time.time()
    run(seat_level="--no-seats" not in sys.argv)
    print(f"{time.time() - t0:.0f}s")
