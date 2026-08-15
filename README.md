# Boston Sports Home Games Calendar

Auto-updating ICS calendar of upcoming home games for seven Boston teams:
Red Sox, Celtics, Patriots, Bruins, Revolution, Boston Legacy FC (NWSL), and BC football.

**Subscribe in Google Calendar:** Settings → *Add calendar* → *From URL* →

```
https://raw.githubusercontent.com/mclarkelauer/boston-sports-calendar/main/boston_sports_home_games.ics
```

Google refreshes subscribed calendars on its own schedule (roughly every 12–24 hours).
The same URL works in Apple Calendar, Outlook, Thunderbird, etc.

## Choosing teams

Teams are configured in `teams.toml` — flip `enabled = true/false` to add or
remove one. Besides the seven defaults, ready-to-enable entries exist for the
Boston Cannons (PLL) and BC/BU/Northeastern/Harvard men's and women's hockey
and BC basketball. The daily cron run picks up changes; run
`./update_and_push.sh` to apply immediately.

## How it works

- `update_calendar.py` pulls each team's schedule from ESPN's public JSON API
  (`site.api.espn.com`), keeps upcoming home games only, and writes
  `boston_sports_home_games.ics`. Season years are computed from the current date,
  so it rolls over to new seasons automatically as ESPN publishes them.
- Every event includes ticket search links (StubHub, Ticketmaster, Vivid Seats)
  in the description, built from team + opponent + date.
- Games without an announced start time (`timeValid: false`) become all-day
  events marked "(time TBD)"; they get real times automatically once announced.
- Timed events are 3 hours long, in America/New_York.
- Event UIDs are stable (ESPN event IDs), so calendar apps update events in place
  instead of duplicating them.
- `update_and_push.sh` runs daily from cron on Matt's machine
  (`15 6 * * *`, logs to `update.log`): regenerates the file and pushes only
  when it changed. If every feed fails, the existing file is kept.

## Manual run

```bash
python3 update_calendar.py
```
