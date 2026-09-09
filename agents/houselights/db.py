"""ClickHouse layer for Houselights.

Runs on embedded ClickHouse (chdb) by default so the whole thing ships as one process; set
CLICKHOUSE_HOST to point the same SQL at ClickHouse Cloud or any server (clickhouse-connect).
Every snapshot the sweep writes is appended, never overwritten, so sell-through is a time series.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOTS = Path(os.environ.get("HOUSELIGHTS_SNAPSHOTS", ROOT / "data" / "snapshots"))
DB_PATH = os.environ.get("HOUSELIGHTS_DB", str(ROOT / "data" / "chdb"))

SCHEMA = [
    "CREATE DATABASE IF NOT EXISTS houselights",
    """CREATE TABLE IF NOT EXISTS houselights.sessions (
        snapshot_ts DateTime, theatre_id LowCardinality(String), theatre_name String,
        film_id UInt32, film String, session_id UInt32, start DateTime, auditorium String,
        experience String, seats_remaining Nullable(UInt16), sold_out UInt8, buy_url String
    ) ENGINE = MergeTree ORDER BY (theatre_id, film_id, start, snapshot_ts)""",
    """CREATE TABLE IF NOT EXISTS houselights.seats (
        snapshot_ts DateTime, theatre_id LowCardinality(String), theatre_name String,
        session_id UInt32, session_start DateTime, row LowCardinality(String), seat String,
        seat_id UInt32, col Nullable(UInt16), seat_type LowCardinality(String),
        status LowCardinality(String)
    ) ENGINE = MergeTree ORDER BY (theatre_id, session_id, row, snapshot_ts)""",
    # Row-level sell-through, maintained by ClickHouse itself on every insert.
    """CREATE MATERIALIZED VIEW IF NOT EXISTS houselights.row_sellthrough
        ENGINE = SummingMergeTree ORDER BY (theatre_id, session_id, session_start, row, snapshot_ts)
        AS SELECT snapshot_ts, theatre_id, theatre_name, session_id, session_start, row,
            countIf(status = 'Available') AS free, countIf(status != 'Available') AS taken
        FROM houselights.seats GROUP BY snapshot_ts, theatre_id, theatre_name, session_id,
            session_start, row""",
    "CREATE TABLE IF NOT EXISTS houselights.loaded (path String) ENGINE = MergeTree ORDER BY path",
]


class _Chdb:
    def __init__(self):
        from chdb import session
        Path(DB_PATH).mkdir(parents=True, exist_ok=True)
        self.s = session.Session(DB_PATH)

    def exec(self, sql):
        self.s.query(sql)

    def query(self, sql, fmt="JSONEachRow"):
        return str(self.s.query(sql, fmt))


class _Server:
    def __init__(self):
        import clickhouse_connect
        self.c = clickhouse_connect.get_client(
            host=os.environ["CLICKHOUSE_HOST"], port=int(os.environ.get("CLICKHOUSE_PORT", 8443)),
            username=os.environ.get("CLICKHOUSE_USER", "default"),
            password=os.environ.get("CLICKHOUSE_PASSWORD", ""), secure=True)

    def exec(self, sql):
        self.c.command(sql)

    def query(self, sql, fmt="JSONEachRow"):
        return self.c.raw_query(sql, fmt=fmt).decode("utf-8", "replace")


_DB = None


def db():
    global _DB
    if _DB is None:
        _DB = _Server() if os.environ.get("CLICKHOUSE_HOST") else _Chdb()
        for stmt in SCHEMA:
            _DB.exec(stmt)
        load_new_snapshots()
    return _DB


def load_new_snapshots():
    """Append every snapshot file not yet loaded. Idempotent: the loaded table remembers paths."""
    d = _DB
    done = {r.strip().strip('"') for r in d.query("SELECT path FROM houselights.loaded", "CSV").splitlines()}
    n = 0
    for p in sorted(glob.glob(str(SNAPSHOTS / "*.sessions.jsonl"))):
        if p in done:
            continue
        path = p.replace("\\", "/")
        d.exec(f"""INSERT INTO houselights.sessions
            SELECT parseDateTimeBestEffort(snapshot_ts), theatre_id, theatre_name, film_id, film,
                   session_id, parseDateTimeBestEffort(start), auditorium, experience,
                   seats_remaining, sold_out, buy_url
            FROM file('{path}', JSONEachRow)""")
        seats = path.replace(".sessions.jsonl", ".seats.jsonl")
        if os.path.exists(seats) and os.path.getsize(seats) > 0:
            d.exec(f"""INSERT INTO houselights.seats
                SELECT parseDateTimeBestEffort(snapshot_ts), theatre_id, theatre_name, session_id,
                       parseDateTimeBestEffort(session_start), row, seat, seat_id, col, seat_type,
                       status
                FROM file('{seats}', JSONEachRow)""")
        d.exec(f"INSERT INTO houselights.loaded VALUES ('{p}')")
        n += 1
    return n


def sql(query: str, fmt: str = "JSONEachRow") -> str:
    return db().query(query, fmt)
