# flightwatch

Daily fare-polling tool for a specific trip: SFO to Japan, out Fri 2027-05-14,
back Sun 2027-05-23 (open jaw, into HND out of KIX). Runs free on GitHub
Actions — no server, no database. It appends each day's fares to an
append-only CSV (`data/history.csv`) and fires Telegram alerts based on
statistical triggers (percentile / new-low / drop-vs-median), not raw price
change, so a number can be judged against its own history instead of vibes.

`config.yaml` holds the routes being tracked and all alert thresholds — it's
the file to edit for day-to-day tuning. `providers.py` adapts Amadeus and
SerpApi, but **Amadeus decommissioned its self-service portal on
2026-07-17 and all keys are disabled** — it is not usable and not the
default. SerpApi is the only working provider: ~100 free searches/month,
so 5 routes needs an every-other-day cron to stay in the free tier.
`tracker.py` does poll → append → evaluate → alert; `analyze.py` produces
reports and the `docs/data.json` the static site reads.

## Running tests

All three run fully offline — no API keys, no network calls:

```bash
python test_logic.py                          # 14 assertions on trigger rules
python test_e2e.py                             # 45-day x 5-route simulation
python tracker.py --replay data/history.csv    # re-score stored history against current config.yaml
```

`--replay` is the threshold-tuning workflow: change a number in
`config.yaml`, rerun it, see what would have fired historically.

## Constraints that matter

- **Route `id` values are permanent join keys** into `data/history.csv`.
  Never rename/reuse one for a different itinerary — it silently
  contaminates that route's percentile history.
- **`max_stops` counts per direction, not summed across the round trip**
  (was a bug — one connection each way used to score as 2 and would wrongly
  reject a normal itinerary).
- **PTO cost is per-route (`pto` field), cap is 6 weekdays.** Routes over cap
  stay in `config.yaml` as priced *levers* (what a 7th day would cost), not
  live candidates — don't treat every tracked route as bookable.
- **Statistical rules need `min_observations` (12) total history for the
  route AND `min_obs_in_window` (8) inside the specific window** — both
  gates matter; the window one exists because a route with old history plus
  one recent row could otherwise report a false "lowest in 30 days" against
  a sample of one.
- **Cooldown is keyed per route, not per route+rule.** Keying it per rule let
  NEW_LOW and PERCENTILE alternate down a slow decline and alert almost
  daily (measured: 29 vs 15 notification days over a 45-day sim). Also
  respects `cooldown_override_pct` (5%) and the hard cap
  `max_alerts_per_route_per_month` (6, FLOOR exempt).
- **`FLOOR` (price ≤ `book_now_usd`, $900) ignores history and the
  `ignore_above_usd` ($1,500) ceiling** — it's the one rule that always gets
  through.
- **Rules evaluate in fixed order, first match wins per route per run:**
  FLOOR → NEW_LOW → PERCENTILE → DROP.
- **A manual "Run workflow" on a cron day is skipped by default** — there's
  a same-day guard in `tracker.py` that skips logging a duplicate
  observation for a route already polled that day. `--force` overrides it
  to log anyway; use it deliberately, since a duplicate row inflates `n`
  and skews percentiles.
- **Total blindness (every route returns zero offers) must alert, not fail
  silently** — this was a real bug; a single-route failure should still only
  warn.
- **CSV over SQLite is deliberate** — it diffs in git, so the daily commit is
  a versioned snapshot. Don't swap the storage format without preserving
  that property.
- Keep the native Google Flights alerts on regardless — this tool is the
  history/percentile layer on top, not a replacement for a working free
  alert.

## Local dev

- Activate the venv in every new terminal (`source .venv/bin/activate`) —
  it's not inherited across sessions.
- Serve `docs/` with `python -m http.server` rather than opening
  `index.html` directly; `file://` blocks the page's fetch of
  `docs/data.json`.
- Never commit `.venv`, `__pycache__`, or simulated/test history — only
  real observations belong in `data/history.csv`.
