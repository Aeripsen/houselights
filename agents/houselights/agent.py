"""Houselights: a Gemini agent (Google ADK) that reads every seat of a 70mm engagement in ClickHouse.

The questions an exhibitor's film programmer actually asks, answered from seat-level data instead
of a weekly gross: how fast is each house selling through, which rows carry the demand, how many
days of runway are left before the engagement ends with no extension loaded, and where can a
party of N still sit together. Every number the agent says comes back from a ClickHouse query;
the deterministic tools below are the only way it can get one.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from google.adk.agents import LlmAgent, SequentialAgent

from . import cineplex as cpx
from . import db

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
FILM_ID = CONFIG["film_id"]
MODEL = os.environ.get("HOUSELIGHTS_MODEL", "gemini-3.6-flash")


def _rows(sql):
    out = db.sql(sql)
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def run_clickhouse_sql(query: str) -> dict:
    """Run a read-only ClickHouse SQL query against the houselights database and return rows.

    Tables: houselights.sessions (one row per session per snapshot: theatre_id, theatre_name,
    film_id, film, session_id, start, auditorium, experience, seats_remaining, sold_out,
    snapshot_ts) and houselights.seats (one row per seat per session per snapshot: row, seat, col,
    seat_type, status which is 'Available' or taken, session_start). houselights.row_sellthrough is
    a materialized view with free/taken per row per session per snapshot. Only SELECT/WITH queries.
    """
    q = query.strip().rstrip(";")
    if not q.lower().startswith(("select", "with", "show", "describe", "explain")):
        return {"error": "read-only: only SELECT / WITH / SHOW / DESCRIBE queries are allowed"}
    try:
        rows = _rows(q + " LIMIT 200" if " limit " not in q.lower() else q)
        return {"rows": rows, "row_count": len(rows)}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:800]}


def engagement_overview() -> dict:
    """Sell-through of the watched film at every house in the latest snapshot: sessions, seats
    remaining, sold-out sessions, first and last bookable date, and how far ahead each house sells
    OTHER films (if other films are bookable past the film's last date, the run is ending, not
    the calendar)."""
    latest = "(SELECT max(snapshot_ts) FROM houselights.sessions)"
    film = _rows(f"""
        SELECT theatre_name, count() AS sessions, sum(seats_remaining) AS seats_left,
               countIf(sold_out = 1) AS sold_out_sessions,
               toString(min(start)) AS first_show, toString(max(start)) AS last_show,
               round(avg(seats_remaining), 1) AS avg_seats_remaining_per_session
        FROM houselights.sessions
        WHERE film_id = {FILM_ID} AND snapshot_ts = {latest}
        GROUP BY theatre_name ORDER BY seats_left ASC""")
    others = _rows(f"""
        SELECT theatre_name, toString(max(start)) AS other_films_bookable_until,
               uniq(film) AS other_films
        FROM houselights.sessions
        WHERE film_id != {FILM_ID} AND snapshot_ts = {latest}
        GROUP BY theatre_name""")
    return {"film": CONFIG["film_name"], "snapshot": _rows(f"SELECT toString({latest}) AS ts")[0]["ts"],
            "houses": film, "other_films_horizon": others}


def sellthrough_by_day(theatre_name_like: str = "") -> dict:
    """Seats remaining per show date for the watched film, per house, with weekday, so weekend
    versus weekday demand and the end of the run are visible. Optional substring filter on house."""
    where = f"AND theatre_name ILIKE '%{theatre_name_like}%'" if theatre_name_like else ""
    rows = _rows(f"""
        SELECT theatre_name, toDate(start) AS show_date, toDayOfWeek(start) AS iso_weekday,
               count() AS sessions, sum(seats_remaining) AS seats_left,
               countIf(sold_out = 1) AS sold_out
        FROM houselights.sessions
        WHERE film_id = {FILM_ID} AND snapshot_ts = (SELECT max(snapshot_ts) FROM houselights.sessions)
        {where}
        GROUP BY theatre_name, show_date, iso_weekday ORDER BY theatre_name, show_date""")
    return {"rows": rows}


def row_demand(theatre_name_like: str = "Vaughan") -> dict:
    """Which rows are taken first: per row, seats taken versus free across all sessions of the
    watched film at a seat-level house (latest snapshot). Uses the row_sellthrough materialized
    view. Reveals the back-to-front selling pattern and where the price signal is."""
    rows = _rows(f"""
        SELECT row, sum(taken) AS taken_seats, sum(free) AS free_seats,
               round(100 * taken_seats / (taken_seats + free_seats), 1) AS pct_taken
        FROM houselights.row_sellthrough
        WHERE theatre_name ILIKE '%{theatre_name_like}%'
          AND snapshot_ts = (SELECT max(snapshot_ts) FROM houselights.seats)
        GROUP BY row ORDER BY row""")
    return {"house_filter": theatre_name_like, "rows": rows}


def find_contiguous_blocks(party_size: int = 7, rows: str = "F,G,H,I,J",
                           weekends_only: bool = True, theatre_name_like: str = "") -> dict:
    """Every session where `party_size` seats are still free side by side in one of `rows`,
    computed inside ClickHouse with array functions (a gap in seat columns is an aisle and breaks a
    block; wheelchair and companion seats never count). Latest snapshot only."""
    accept = ",".join("'" + r.strip().upper() + "'" for r in rows.split(",") if r.strip())
    wk = "AND toDayOfWeek(session_start) IN (5, 6, 7)" if weekends_only else ""
    house = f"AND theatre_name ILIKE '%{theatre_name_like}%'" if theatre_name_like else ""
    q = f"""
        WITH per_row AS (
            SELECT theatre_name, session_id, session_start, row,
                   arraySort(x -> x.1, groupArray((col, status = 'Available'
                        AND seat_type NOT IN ('Wheelchair', 'Companion'), seat))) AS s
            FROM houselights.seats
            WHERE snapshot_ts = (SELECT max(snapshot_ts) FROM houselights.seats)
              AND row IN ({accept}) AND col IS NOT NULL {wk} {house}
            GROUP BY theatre_name, session_id, session_start, row
        ),
        runs AS (
            SELECT theatre_name, session_id, session_start, row,
                   arraySplit((x, i) -> (i = 1 OR x.2 != s[i - 1].2 OR x.1 != s[i - 1].1 + 1),
                              s, arrayEnumerate(s)) AS groups
            FROM per_row
        )
        SELECT theatre_name, toString(session_start) AS session_start, row,
               arrayMap(g -> g.3, best) AS seats
        FROM (
            SELECT theatre_name, session_id, session_start, row,
                   arrayFirst(g -> g[1].2 AND length(g) >= {int(party_size)}, groups) AS best
            FROM runs
        )
        WHERE length(best) > 0
        ORDER BY session_start, row"""
    try:
        found = _rows(q)
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:800]}
    return {"party_size": party_size, "rows_accepted": rows, "weekends_only": weekends_only,
            "matches": found, "match_count": len(found)}


def live_seats_remaining(theatre_id: str, show_date: str) -> dict:
    """Hit the exhibitor's public API right now for one house and one date (YYYY-MM-DD) and return
    the current seats remaining per session of the watched film. Live, not from ClickHouse."""
    if theatre_id not in CONFIG["theatres"]:
        return {"error": "unknown theatre_id", "known": CONFIG["theatres"]}
    sess = [s for s in cpx.showtimes(theatre_id, show_date) if s["film_id"] == FILM_ID]
    return {"theatre": CONFIG["theatres"][theatre_id], "date": show_date,
            "sessions": [{"start": s["start"], "seats_remaining": s["seats_remaining"],
                          "sold_out": s["sold_out"], "experience": s["experience"]} for s in sess]}


def take_snapshot(theatre_id: str = "7408") -> dict:
    """Pull a fresh snapshot for one house (all its bookable dates, seat-level if the house is a
    seat-level house), append it to ClickHouse, and report how many rows landed. A few dozen polite
    API calls; use when the user wants numbers newer than the latest snapshot."""
    from . import sweep
    lines = []
    sweep.run(seat_level=True, log=lines.append, theatres=[theatre_id])
    n = db.load_new_snapshots()
    return {"files_loaded": n, "log_tail": lines[-3:]}


INSTRUCTION = f"""You are Houselights, the film programmer's analyst for a theatrical engagement.
Film: {CONFIG['film_name']} on IMAX 70mm at {len(CONFIG['theatres'])} Cineplex houses in Canada.
Seat-level data exists for: {', '.join(CONFIG['theatres'][t] for t in CONFIG['seat_level_theatres'])}.
Theatre ids: {json.dumps(CONFIG['theatres'])}.

Rules:
- Every number you state must come from a tool call in this turn. Never estimate from memory.
- Start with engagement_overview for any question about the run as a whole; use sellthrough_by_day,
  row_demand and find_contiguous_blocks for detail; write your own SQL with run_clickhouse_sql only
  when no tool answers the question. Use live_seats_remaining only when asked for right-now numbers.
- Think like an exhibitor: seats remaining is inventory, sold-out weekend sessions are money left on
  the table, a last bookable date earlier than other films' horizon means the run ends unless a
  programmer loads more dates. Say what to do (extend, add a session, move a slot) and the numbers
  behind it.
- Be concise and concrete: short paragraphs, a compact table when comparing houses, no filler.
"""

root_agent = LlmAgent(
    name="houselights",
    model=MODEL,
    description="Seat-level demand analyst for a 70mm theatrical engagement, on ClickHouse.",
    instruction=INSTRUCTION,
    tools=[engagement_overview, sellthrough_by_day, row_demand, find_contiguous_blocks,
           run_clickhouse_sql, live_seats_remaining, take_snapshot],
)

# A fixed three-stage pipeline for the weekly programming brief: facts, seats, memo.
# Deterministic order, each stage reads the previous stage's output from session state.
demand_stage = LlmAgent(
    name="demand_analyst", model=MODEL, output_key="demand_facts",
    instruction="Call engagement_overview and sellthrough_by_day (no filter). Report, as terse "
                "bullet facts with numbers: per house seats remaining and sold-out sessions, the "
                "last bookable date versus other films' horizon, weekend vs weekday demand.",
    tools=[engagement_overview, sellthrough_by_day])
seat_stage = LlmAgent(
    name="seat_analyst", model=MODEL, output_key="seat_facts",
    instruction="Call row_demand for Vaughan and for Square One, then find_contiguous_blocks with "
                "party_size 7 and rows F,G,H,I,J weekends_only true. Report as terse bullets: "
                "which rows sell first, percent taken per row band, and how many weekend sessions "
                "still seat a party of 7 together in F-J. Demand facts so far: {demand_facts}",
    tools=[row_demand, find_contiguous_blocks])
memo_stage = LlmAgent(
    name="programmer", model=MODEL, output_key="memo",
    instruction="Write the programming brief for the exhibitor's film programmer from these facts "
                "only. Facts: {demand_facts}\n\nSeats: {seat_facts}\n\nFormat: title line, three "
                "sections (Where the money is, Runway, Recommended actions with the number behind "
                "each). Under 250 words. No speculation beyond the facts.")
programming_brief = SequentialAgent(
    name="programming_brief", sub_agents=[demand_stage, seat_stage, memo_stage],
    description="Deterministic three-stage weekly programming brief: demand facts, seat facts, memo.")
