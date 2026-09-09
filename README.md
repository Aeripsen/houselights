---
title: Houselights
emoji: 🎞️
colorFrom: gray
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# Houselights

A Gemini agent, built with Google's Agent Development Kit, that reads every seat of a theatrical
engagement out of ClickHouse and tells the exhibitor's film programmer what to do about it:
extend the run, add a session, move a slot, price a row. Before the houselights come up.

Built for the Agentic Cinema hackathon, ClickHouse track. Live demo: the ADK web UI, pick the
`houselights` agent and ask it anything about the run, or pick `houselights_brief` for the fixed
three-stage programming brief.

## Why this exists

In September 2026 I tried to get seven friends into good rows for Christopher Nolan's *The Odyssey*
on IMAX 70mm in Toronto. Cineplex has two 70mm houses here, Vaughan and Square One, and the seat
maps were brutal: the houses sell back to front, the good rows (F to J) go first, and what is left
is the front. I wrote a watcher against the same public API the Cineplex website uses, checked all
92 remaining Vaughan sessions at the seat level, and found exactly two with seven seats together
in F to J. Both weekday mornings, both hugging a wall.

Two other things fell out of that data. The 70mm engagement is one national block: eight houses
from Langley BC to Halifax, all ending on the same date, loaded in one go. And the run's last
bookable date was earlier than the date those same houses were already selling other films into.
The engagement was ending, quietly, unless someone loaded more dates.

That is the exhibitor's problem, not mine. A film programmer decides whether to extend a run and
where to add sessions from weekly grosses and gut feel, while seat-level demand is sitting in their
own ticketing system, refreshed every few minutes. Houselights puts that data in ClickHouse and
gives the programmer an agent that answers from it.

## What it does

The sweep (`agents/houselights/sweep.py`) takes a snapshot of the whole engagement: every bookable
date at every house, every session of every film (so the agent can see what else the house sells
and how far ahead), and for the seat-level houses, every seat of every session of the watched
film. Snapshots are appended to ClickHouse, never overwritten, so sell-through is a time series.

The agent (`agents/houselights/agent.py`) is a Google ADK `LlmAgent` on Gemini with seven tools.
Every number it says comes from a tool call; the deterministic tools are the only way it can get one.

| Tool | What it runs |
|---|---|
| `engagement_overview` | Per-house seats remaining, sold-out sessions, last bookable date versus the horizon other films sell to |
| `sellthrough_by_day` | Seats remaining per show date and weekday, per house |
| `row_demand` | Taken vs free per row from the `row_sellthrough` materialized view |
| `find_contiguous_blocks` | Sessions with N seats together in accepted rows, computed inside ClickHouse with `groupArray`, `arraySort` and `arraySplit` (a gap in seat columns is an aisle and breaks the block) |
| `run_clickhouse_sql` | Read-only SQL for anything the fixed tools do not cover |
| `live_seats_remaining` | Hits the exhibitor's public API right now for one house and date |
| `take_snapshot` | Pulls a fresh snapshot for one house and appends it to ClickHouse |

`houselights_brief` is an ADK `SequentialAgent`: a demand analyst, a seat analyst, and a
programmer, in a fixed order, each reading the previous stage's facts from session state and the
last one writing a memo under 250 words with the number behind every recommendation.

## ClickHouse

Schema in `agents/houselights/db.py`:

- `houselights.sessions`, MergeTree ordered by (theatre, film, start, snapshot)
- `houselights.seats`, MergeTree ordered by (theatre, session, row, snapshot), one row per seat
  per session per snapshot
- `houselights.row_sellthrough`, a SummingMergeTree materialized view ClickHouse maintains itself
  on every insert
- snapshots are loaded straight from JSONL with the `file()` table function and `JSONEachRow`

It runs on embedded ClickHouse (`chdb`) by default so the whole thing ships as one process. Set
`CLICKHOUSE_HOST`, `CLICKHOUSE_USER` and `CLICKHOUSE_PASSWORD` and the same SQL runs against
ClickHouse Cloud through `clickhouse-connect`.

## Run it

```bash
pip install -r requirements.txt
export GOOGLE_API_KEY=...            # Gemini API key from a Google Cloud project
export GOOGLE_GENAI_USE_VERTEXAI=FALSE
adk web agents                       # http://localhost:8000, pick houselights
```

To refresh the data: `python -m agents.houselights.sweep` (about three minutes, roughly 500
polite calls to the public API; the watched film and houses are in `config.json`). The repo
ships one full snapshot, taken 2026-09-09 20:03 UTC: 5,033 sessions across the eight houses and
50,235 seat states for the two Toronto houses.

Docker: `docker build -t houselights . && docker run -p 7860:7860 -e GOOGLE_API_KEY=... houselights`.

## Honest limits

- Read-only, by design and by the exhibitor's terms: it never holds a seat, never buys.
- One exhibitor's API. The schema is generic (any ticketing export with session and seat rows
  loads the same way), the client is not.
- The seat-level sweep covers the two Toronto houses; the other six are session-level.

## License

MIT.
