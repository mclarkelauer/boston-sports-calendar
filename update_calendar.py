#!/usr/bin/env python3
"""Regenerate boston_sports_home_games.ics from ESPN's public schedule APIs.

Fetches upcoming home games for seven Boston teams, adds ticket-search links
(StubHub / Ticketmaster / Vivid Seats) to each event, and writes the combined
ICS calendar. Designed to run unattended from cron: a team whose feed fails is
skipped with a warning; the file is only rewritten when at least one event was
fetched.
"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

OUT_FILE = Path(__file__).parent / "boston_sports_home_games.ics"
API = "https://site.api.espn.com/apis/site/v2/sports"
EASTERN = ZoneInfo("America/New_York")
GAME_HOURS = 3


def season_params(now):
    """Per-league query-param sets to request; merged by event id."""
    y = now.year
    nba_nhl = y + 1 if now.month >= 7 else y  # season named by its ending year
    nfl = y if now.month >= 3 else y - 1
    cfb = y if now.month >= 2 else y - 1
    return {
        "mlb": [{"season": y}, {"season": y + 1}],
        "nba": [{"season": nba_nhl, "seasontype": 2}, {"season": nba_nhl + 1, "seasontype": 2}],
        "nfl": [
            {"season": nfl, "seasontype": 1, "_label": " (preseason)"},
            {"season": nfl, "seasontype": 2},
            {"season": nfl + 1, "seasontype": 2},
        ],
        "nhl": [{}, {"season": nba_nhl + 1, "seasontype": 2}],
        "soccer": [{"fixture": "true"}],
        "cfb": [{"season": cfb, "seasontype": 2}, {"season": cfb + 1, "seasontype": 2}],
    }


TEAMS = [
    # key, display name, ticket-search name, emoji, ESPN sport path, ESPN team id, param group
    ("redsox", "Red Sox", "Boston Red Sox", "⚾", "baseball/mlb", "bos", "mlb"),
    ("celtics", "Celtics", "Boston Celtics", "🏀", "basketball/nba", "bos", "nba"),
    ("patriots", "Patriots", "New England Patriots", "🏈", "football/nfl", "ne", "nfl"),
    ("bruins", "Bruins", "Boston Bruins", "🏒", "hockey/nhl", "bos", "nhl"),
    ("revs", "Revolution", "New England Revolution", "⚽", "soccer/usa.1", "189", "soccer"),
    ("legacy", "Boston Legacy FC", "Boston Legacy FC", "⚽", "soccer/usa.nwsl", "131562", "soccer"),
    ("bceagles", "BC Football", "Boston College Eagles Football", "🏈", "football/college-football", "103", "cfb"),
]

VTIMEZONE = """BEGIN:VTIMEZONE
TZID:America/New_York
BEGIN:DAYLIGHT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
TZNAME:EDT
DTSTART:19700308T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
TZNAME:EST
DTSTART:19701101T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
END:VTIMEZONE"""


def fetch_json(url):
    # ESPN's edge blocks unknown/browser-ish Python UAs but allows curl's
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.9.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def esc(s):
    return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def fold(line):
    """RFC 5545 line folding at 74 octets."""
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode()) > 74:
            out.append(cur)
            cur = " " + ch
        else:
            cur += ch
    out.append(cur)
    return "\r\n".join(out)


def ticket_links(search_name, opponent, local_dt):
    q = urllib.parse.quote_plus(f"{search_name} vs {opponent} {local_dt.month}/{local_dt.day}/{local_dt.year}")
    return (
        f"Tickets:\nStubHub: https://www.stubhub.com/find/s/?q={q}"
        f"\nTicketmaster: https://www.ticketmaster.com/search?q={q}"
        f"\nVivid Seats: https://www.vividseats.com/search?searchTerm={q}"
    )


def team_events(team, now, all_params):
    key, name, search_name, emoji, sport, team_id, group = team
    events = {}
    for params in all_params[group]:
        label = params.get("_label", "")
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if not k.startswith("_")})
        url = f"{API}/{sport}/teams/{team_id}/schedule" + (f"?{qs}" if qs else "")
        try:
            data = fetch_json(url)
        except Exception as ex:
            print(f"WARN: fetch failed for {name} ({url}): {ex}", file=sys.stderr)
            continue
        # the URL accepts slugs like "bos" but competitors carry numeric ids
        canonical_id = str(data.get("team", {}).get("id", team_id))
        for ev in data.get("events", []):
            comp = ev["competitions"][0]
            competitors = comp.get("competitors", [])
            home = next((c for c in competitors if c.get("homeAway") == "home"), None)
            if not home or str(home["team"]["id"]) != canonical_id:
                continue
            start = datetime.strptime(ev["date"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
            if start < now - timedelta(hours=6):
                continue
            opp = next(
                (c["team"]["displayName"] for c in competitors if c is not home),
                "TBD",
            )
            events[ev["id"]] = {
                "uid": f"{key}-{ev['id']}@boston-sports",
                "start": start.astimezone(EASTERN),
                "time_valid": comp.get("timeValid", True),
                "summary": f"{emoji} {name} vs {opp}{label}",
                "venue": comp.get("venue", {}).get("fullName", ""),
                "description": ticket_links(search_name, opp, start.astimezone(EASTERN)),
            }
    return list(events.values())


def vevent(ev, dtstamp):
    lines = ["BEGIN:VEVENT", f"UID:{ev['uid']}", f"DTSTAMP:{dtstamp}"]
    start = ev["start"]
    if ev["time_valid"]:
        end = start + timedelta(hours=GAME_HOURS)
        lines += [
            f"DTSTART;TZID=America/New_York:{start:%Y%m%dT%H%M%S}",
            f"DTEND;TZID=America/New_York:{end:%Y%m%dT%H%M%S}",
            f"SUMMARY:{esc(ev['summary'])}",
        ]
    else:
        end = start.date() + timedelta(days=1)
        lines += [
            f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
            f"DTEND;VALUE=DATE:{end:%Y%m%d}",
            f"SUMMARY:{esc(ev['summary'] + ' (time TBD)')}",
        ]
    if ev["venue"]:
        lines.append(f"LOCATION:{esc(ev['venue'])}")
    lines.append(f"DESCRIPTION:{esc(ev['description'])}")
    lines.append("END:VEVENT")
    return lines


def main():
    now = datetime.now(timezone.utc)
    dtstamp = f"{now:%Y%m%dT%H%M%SZ}"
    all_params = season_params(now)
    all_events = []
    for team in TEAMS:
        evs = team_events(team, now, all_params)
        print(f"{team[1]}: {len(evs)} upcoming home games")
        if not evs:
            print(f"WARN: no upcoming home games found for {team[1]}", file=sys.stderr)
        all_events += evs
    if not all_events:
        print("ERROR: no events fetched from any feed; keeping existing file", file=sys.stderr)
        sys.exit(1)
    all_events.sort(key=lambda e: e["start"])
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//boston-sports//home-games//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:Boston Sports Home Games",
        "X-WR-TIMEZONE:America/New_York",
        VTIMEZONE,
    ]
    for ev in all_events:
        lines += vevent(ev, dtstamp)
    lines.append("END:VCALENDAR")
    OUT_FILE.write_text("\r\n".join(fold(l) for l in lines) + "\r\n")
    print(f"Wrote {OUT_FILE} with {len(all_events)} events")


if __name__ == "__main__":
    main()
