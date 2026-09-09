"""Read-only client for the public Cineplex web API (the same endpoints www.cineplex.com calls).

Polite by construction: a fixed pause between calls, three retries, never a login, never a hold,
never a purchase. The subscription key is the public web key shipped in Cineplex's own JS bundle.
"""
from __future__ import annotations

import gzip
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

CPX_KEY = "dcdac5601d864addbc2675a2e96cb1f8"
THEATRICAL = "https://apis.cineplex.com/prod/cpx/theatrical/api/v1"
TICKETING = "https://apis.cineplex.com/prod/ticketing/api/v1"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
PAUSE = 0.4


def _get(url, tries=3):
    req = urllib.request.Request(url, headers={
        "Ocp-Apim-Subscription-Key": CPX_KEY, "User-Agent": UA, "Accept": "application/json",
        "Accept-Encoding": "gzip, identity", "Referer": "https://www.cineplex.com/",
    })
    for attempt in range(tries):
        try:
            time.sleep(PAUSE)
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 204:
                    return None
                raw = resp.read()
                if raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                return json.loads(raw) if raw else None
        except (urllib.error.URLError, OSError, ValueError) as e:
            if attempt == tries - 1:
                print("[cpx] GET failed " + url + ": " + str(e))
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def bookable_dates(theatre_id, film_id):
    q = urllib.parse.urlencode({"language": "en", "locationId": theatre_id, "filmId": film_id})
    data = _get(THEATRICAL + "/dates/bookable?" + q)
    return sorted({str(d)[:10] for d in data}) if isinstance(data, list) else []


def showtimes(theatre_id, day):
    """Every online-bookable session of every film at the theatre on `day`."""
    q = urllib.parse.urlencode({"language": "en", "locationId": theatre_id, "date": day})
    data = _get(THEATRICAL + "/showtimes?" + q)
    if not isinstance(data, list):
        return []
    out, seen = [], set()
    for theatre in data:
        for dblock in theatre.get("dates", []):
            for movie in dblock.get("movies", []):
                for exp in movie.get("experiences", []):
                    types = [str(t) for t in exp.get("experienceTypes", [])]
                    for s in exp.get("sessions", []):
                        if s.get("isInThePast") or not s.get("isShowtimeEnabledOnline"):
                            continue
                        sid = s.get("vistaSessionId")
                        if sid in seen:
                            continue
                        seen.add(sid)
                        out.append({
                            "theatre_id": str(theatre_id),
                            "theatre": theatre.get("theatre", ""),
                            "film_id": movie.get("id"),
                            "film": movie.get("name") or movie.get("title") or "",
                            "session_id": sid,
                            "start": s.get("showStartDateTime", ""),
                            "auditorium": s.get("auditorium", ""),
                            "experience": "+".join(types),
                            "seats_remaining": s.get("seatsRemaining"),
                            "sold_out": bool(s.get("isSoldOut")),
                            "buy_url": s.get("ticketingUrl", ""),
                        })
    return out


_LAYOUT = {}


def seat_layout(theatre_id, session_id, auditorium=""):
    """[{label, seats:[{id,label,column,type}]}]; cached per auditorium within a process."""
    key = str(theatre_id) + ":" + auditorium
    if key in _LAYOUT:
        return _LAYOUT[key]
    data = _get(TICKETING + "/theatre/" + str(theatre_id) + "/showtime/" + str(session_id)
                + "/seat-layout")
    if not isinstance(data, dict):
        return None
    rows = []
    for group in ("standardSeats", "dboxSeats", "balconySeats"):
        for r in (data.get(group) or {}).get("rows") or []:
            seats = r.get("seats") or []
            if not seats:
                continue
            label = r.get("label")
            if not label:
                m = re.match(r"[A-Za-z]+", str(seats[0].get("label", "")))
                label = m.group(0) if m else "?"
            rows.append({"label": str(label).upper(), "seats": [
                {"id": s.get("id"), "label": s.get("label"), "column": s.get("column"),
                 "type": s.get("type", "Standard")} for s in seats]})
    _LAYOUT[key] = rows
    return rows


def seat_availability(theatre_id, session_id):
    data = _get(TICKETING + "/theatre/" + str(theatre_id) + "/showtime/" + str(session_id)
                + "/seat-availability?preview=true")
    return (data.get("seatAvailabilities") or {}) if isinstance(data, dict) else None
