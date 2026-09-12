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
  reject a normal itinerary). This is also how Google's own stops filter
  behaves: each leg must independently satisfy the cap.
- **SerpApi's multi-city (`type=3`) first request only sees the outbound
  leg** — `flights`/`total_duration` in that response describe leg 1 alone.
  `price` is already the true round-trip total (Google prices it assuming
  the cheapest matching return), but the return leg's own stops/duration/
  routing stay invisible until you follow that offer's `departure_token` in
  a second request. Picking the lowest-priced return option on that
  follow-up is what reproduces the total already quoted — confirmed
  empirically: a $1,003 offer via a 12.5h Taipei layover matched a return
  also via Taipei at that same $1,003 total. Without the follow-up, a cheap
  fare can silently be paired with an atrocious return routing.
- **Routes with `full_read: true` make that follow-up request; others don't.**
  Full-read routes populate real `stops`/`duration_min` (worst-direction
  count, summed duration) plus `outbound_stops`/`outbound_duration_min` and
  `return_stops`/`return_duration_min` — each leg reported separately,
  exactly as Google's UI shows them, never merged. Non-full-read routes only
  ever get the `outbound_*` fields; `stops`/`duration_min` stay `None`.
  **This doubles SerpApi quota on those routes** (2 requests instead of 1) —
  with 3 full-read + 2 plain routes that's 8 requests/poll, ~120/month on
  the every-other-day cron, over the ~100 free-tier cap. Slow the cron
  further or upgrade tier if quota starts getting hit.
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
- Local credentials (`SERPAPI_KEY`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`) go
  in a gitignored `.env`; `tracker.py` loads it via `python-dotenv` at
  import time (a no-op in CI, which has no `.env` and gets its secrets from
  Actions env vars instead).
- Serve `docs/` with `python -m http.server` rather than opening
  `index.html` directly; `file://` blocks the page's fetch of
  `docs/data.json`.
- Never commit `.venv`, `__pycache__`, or simulated/test history — only
  real observations belong in `data/history.csv`.
