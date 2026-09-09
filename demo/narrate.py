"""Narration for the demo: one wav per segment, Gemini TTS first, edge-tts as the fallback.

Segment starts (seconds) match SEG in demo/index.html: card 0, Q1 20, Q2 70, Q3 120, outro 170.
"""
import base64
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.request
import wave

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).parent / "narration")
OUT.mkdir(parents=True, exist_ok=True)
ENV = pathlib.Path(r"F:\temppcfiles\SEP\PROJECTS\Transcendent\.env").read_text(encoding="utf-8")
KEY = re.search(r"^GEMINI_API_KEY=(.*)$", ENV, re.M).group(1).strip()

SEGMENTS = [
    (0, "This is Houselights. In September I tried to get seven friends into good rows for The Odyssey "
        "on IMAX seventy millimetre in Toronto, and the seat maps said no. The same data says a lot more "
        "to the exhibitor. So I put every seat of the engagement into ClickHouse, and gave the film "
        "programmer a Gemini agent built with Google's Agent Development Kit."),
    (20, "First question: how is the run selling across all eight seventy millimetre houses, and is it "
         "ending? The agent calls engagement overview, a deterministic tool that queries ClickHouse. "
         "Every number it says comes back from a query. Toronto sells hardest, Montreal holds the most "
         "inventory, and every house stops selling on the same date while other films are bookable "
         "further out. That is a run ending, not a calendar."),
    (70, "Second: at Vaughan, which rows sell first? This comes from a materialized view that ClickHouse "
         "maintains itself on every insert. The house sells back to front. Rows F to J are around "
         "eighty percent taken across the run. Rows A and B are under ten. That is a price signal the "
         "exhibitor already owns and does not read."),
    (120, "Third: seven people, together, rows F to J, on a weekend. Contiguous block detection runs "
          "inside ClickHouse with array functions, so an aisle breaks a block and accessible seats never "
          "count. The agent turns what is left into a recommendation: where to add a session, and which "
          "rows to price."),
    (170, "Houselights. Open source, one process, ClickHouse inside. Code on GitHub."),
]


def gemini_tts(text, path):
    body = {"contents": [{"parts": [{"text": "Read this calmly, like a documentary narrator: " + text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Charon"}}}}}
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key=" + KEY,
        data=json.dumps(body).encode(), headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    part = data["candidates"][0]["content"]["parts"][0]["inlineData"]
    pcm = base64.b64decode(part["data"])
    rate = int(re.search(r"rate=(\d+)", part.get("mimeType", "")).group(1)) if "rate=" in part.get("mimeType", "") else 24000
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)


def edge(text, path):
    mp3 = path.with_suffix(".mp3")
    subprocess.run([sys.executable, "-m", "edge_tts", "--voice", "en-US-GuyNeural", "--text", text,
                    "--write-media", str(mp3)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), str(path)], check=True)


for i, (start, text) in enumerate(SEGMENTS):
    path = OUT / f"seg{i}.wav"
    try:
        gemini_tts(text, path)
        src = "gemini"
    except Exception as e:  # noqa: BLE001
        print(f"seg{i}: gemini tts failed ({str(e)[:120]}), using edge-tts")
        edge(text, path)
        src = "edge"
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.strip()
    print(f"seg{i} start={start}s dur={dur}s via {src}")
print("OK", OUT)
