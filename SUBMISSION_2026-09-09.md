# Devpost submission record, Agentic Cinema hackathon (ClickHouse track)

Deadline: 2026-09-09 5:00 PM EDT. Devpost edit page:
https://devpost.com/submit-to/30721-agentic-cinema-the-blockbuster-hackathon/manage/submissions/1176783-houselights-seat-level-demand-agent-for-a-70mm-run/finalization

Public preview: https://devpost.com/software/houselights-seat-level-demand-agent-for-a-70mm-run

## What is filled in (saved on Devpost, 3 of 5 steps)

Project overview
- Project name: Houselights: seat-level demand agent for a 70mm run
- Elevator pitch: A Gemini agent on Google ADK that reads every seat of a national IMAX 70mm engagement out of ClickHouse and tells the exhibitor when to extend, add or move a show.

Project details
- About the project: the story in README.md, sections Inspiration / What it does / How I built it / Challenges / What I learned / What's next
- Built with: python, google-adk, gemini, google-cloud, clickhouse, chdb, fastapi, uvicorn, sql, materialized-views, cineplex-api, playwright
- Try it out links: https://github.com/Aeripsen/houselights and http://167.99.185.172:8500/
- Video demo link: https://youtu.be/yYp5YB7KAfs (uploaded by Sepehr by drag-and-drop, set Public 4:57 PM)

Additional info
- Submitter type Individual, organization N/A, government employee No, Canada, Ontario, project New
- Partner track: Clickhouse
- Team size 1
- Repo URL: https://github.com/Aeripsen/houselights (MIT, detected by GitHub)
- Hosted URL: http://167.99.185.172:8500/ (adk web on the droplet, port opened in ufw 2026-09-09)
- Google Cloud products: Gemini API (gemini-3.6-flash) on a Google Cloud project, Google Agent Development Kit (LlmAgent, SequentialAgent, adk web)
- Other tools: ClickHouse via chdb (MergeTree, SummingMergeTree materialized view, file() + JSONEachRow, array functions), clickhouse-connect path for ClickHouse Cloud, Python 3.12, Cineplex public API, Playwright + ffmpeg
- First time using ClickHouse: Yes. IBM / Grafana / Parallel / Replit: N/A

## Submitted 2026-09-09 4:55 PM EDT. Devpost said: Project submitted! Continue to edit until 5:00 PM EDT.

## What was left before that (done)

1. Upload demo/houselights_demo.mp4 to YouTube, visibility Public.
   Title: Houselights: a Gemini agent over seat-level cinema data in ClickHouse (Agentic Cinema hackathon)
   Description: Demo of Houselights for the Agentic Cinema hackathon, ClickHouse track. A Google ADK agent on Gemini 3.6 Flash answers a film programmer's questions from seat-level engagement data in ClickHouse: sell-through across eight IMAX 70mm houses, which rows sell first, and where seven people can still sit together. Code: https://github.com/Aeripsen/houselights
2. Devpost > Project details > Video demo link: paste the YouTube URL > Save & continue.
3. Devpost > Submit: tick the Official Rules box > Submit project.

## Known limits, stated honestly on the page
- Hosted on a DigitalOcean droplet, not Cloud Run: Google Cloud billing on this account is a closed trial, so Vertex and Cloud Run were not available without a card.
- ClickHouse runs embedded (chdb), not ClickHouse Cloud: creating a ClickHouse Cloud account was not something I do on his behalf. The clickhouse-connect path is in db.py.
- Video is silent with English on screen; the third answer shows tool calls but its final text did not render in the recording.
