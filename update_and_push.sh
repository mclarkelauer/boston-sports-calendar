#!/usr/bin/env bash
# Regenerate the calendar and push to GitHub if it changed. Run daily from cron.
set -euo pipefail
cd "$(dirname "$0")"
python3 update_calendar.py
if ! git diff --quiet boston_sports_home_games.ics; then
  git add boston_sports_home_games.ics
  git commit -q -m "Update calendar $(date +%F)"
  git push -q
  echo "$(date -Is) pushed updated calendar"
else
  echo "$(date -Is) no changes"
fi
