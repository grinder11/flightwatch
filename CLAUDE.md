# flightwatch

Fare-polling tool for a specific trip: SFO to Japan, out Fri 2027-05-14,
back Sun 2027-05-23 (open jaw, into HND out of KIX). Runs free on GitHub
Actions on an **every-other-day cron, not daily** — no server, no database.
It appends each poll's fares to an append-only CSV (`data/history.csv`) and
fires Telegram alerts based on statistical triggers (percentile / new-low /
drop-vs-median), not raw price change, so a number can be judged against
its own history instead of vibes.

`config.yaml` holds the routes being tracked (currently 8 — see its own
comments for the live breakdown and current SerpApi quota math, rather than
trusting a number restated here) and all alert thresholds; it's the file to
edit for day-to-day tuning. `providers.py` adapts Amadeus and SerpApi, but
**Amadeus decommissioned its self-service portal on 2026-07-17 and all keys
are disabled** — it is not usable and not the default. SerpApi is the only
working provider, ~100 free searches/month. `tracker.py` does poll → append
→ evaluate → alert; `analyze.py` produces reports and the `docs/data.json`
the static site (live at https://grinder11.github.io/flightwatch/) reads.

## Running tests

All three run fully offline — no API keys, no network calls:

```bash
python test_logic.py                          # assertions on trigger rules
python test_e2e.py                             # 45-day, multi-route simulation
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
- **SerpApi's offer list can be incomplete vs. Google's own live UI for the
  identical search** — confirmed empirically: a nonstop query returned only
  2 of 3 nonstop outbound options the browser showed, dropping the cheapest
  (JAL). Matters most for stops-allowed routes (a cheaper single leg could
  go unseen); matters less for full_read/nonstop routes specifically, since
  those answer "cheapest matched round trip" — the missing JAL leg didn't
  have a comparable nonstop return partner anyway (~$3k full-nonstop total
  via JAL, worse than the ~$1,579 pairing SerpApi did surface). No fix on
  our end short of a different data source; just don't treat "cheapest
  offer we got" as provably "cheapest offer that exists."
- **Routes with `full_read: true` make that follow-up request; others don't.**
  Full-read routes populate real `stops`/`duration_min` (worst-direction
  count, summed duration) plus per-leg `outbound_*`/`return_*` fields
  (stops, duration, and local departure/arrival clock times) — each leg
  reported separately, exactly as Google's UI shows them, never merged.
  Non-full-read routes only ever get the `outbound_*` fields.
  **This doubles SerpApi quota on those routes** (2 requests instead of 1).
  Current mix is over the ~100/month free tier even on the every-other-day
  cron — check `config.yaml`'s quota comment before adding another
  `full_read`/`nonstop` route, don't just assume there's headroom.
- **`target: true` and `role: baseline` in `config.yaml` drive the site's
  categorization** (`docs/index.html`, "The Trip" / "7-Day Variants" /
  "Nonstop Variants" / "Baselines") and what counts toward the "cheapest
  now" badge. A new route with neither field set defaults to a regular
  candidate — fine for a real bookable variant, wrong for a comparison-only
  route (it would then count toward "cheapest," which is exactly the bug
  the badge exists to avoid). Set `role: baseline` deliberately on anything
  that isn't a real option for this trip.
- **The alert engine assumes one observation per calendar day** —
  `min_observations`, `min_obs_in_window`, and every `*_window_days` are
  row counts, not distinct-day counts. Polling more than once a day (even
  via `--force`) silently changes what those thresholds mean:
  `min_observations: 12` would arm in 6 days instead of 12, and a "30-day
  window" would hold ~60 samples instead of 30. `analyze.py`'s chart already
  collapses same-day rows to a daily low for *display* (`daily_lows()`),
  but `tracker.py`'s alert engine does not — don't increase polling
  frequency past once/day without redesigning the window logic to match.
- **Schema changes to `FIELDS` in `tracker.py` need the migration path
  exercised, not just the list edited.** `data/history.csv` holds real
  committed observations now, under whatever header was live when they
  were written — `append_history()` calls `_migrate_history_header()`
  first specifically so a grown `FIELDS` list rewrites the header and
  backfills old rows' new columns as blank, instead of silently appending
  misaligned columns under a stale header. Confirm the migration ran
  (`git diff data/history.csv` should show only header + blank new columns,
  no data altered) before trusting a schema change.
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
  daily — see `VALIDATION.md` for the original measurement. Also respects
  `cooldown_override_pct` (5%) and the hard cap
  `max_alerts_per_route_per_month` (6, FLOOR exempt).
- **`FLOOR` (price ≤ `book_now_usd`, $900) ignores history and the
  `ignore_above_usd` ($1,500) ceiling** — it's the one rule that always gets
  through.
- **Rules evaluate in fixed order, first match wins per route per run:**
  FLOOR → NEW_LOW → PERCENTILE → DROP.
- **A manual "Run workflow" on a day already polled is skipped by default**
  — there's a same-day guard in `tracker.py` that skips logging a duplicate
  observation for a route already polled that day. `--force` overrides it
  to log anyway; use it deliberately, since a duplicate row inflates `n`
  and skews percentiles. Triggering a manual run on a day the cron *hasn't*
  fired is the opposite case and needs no `--force` at all — the guard only
  blocks a second row, not a first one, so this is a safe way to backfill a
  gap day without touching statistics or the cron's own schedule.
- **The cron's `*/2` is day-of-month parity (odd calendar days), not
  "2 days after last run."** `cron: "10 14 */2 * *"` fires on the 1st, 3rd,
  5th... of the month regardless of when it last actually ran, so a month
  boundary can occasionally give a 1-day or 3-day gap instead of 2. Manual
  `workflow_dispatch` runs don't affect this schedule either way.
- **Total blindness (every route returns zero offers) must alert, not fail
  silently** — this was a real bug; a single-route failure should still only
  warn.
- **CSV over SQLite is deliberate** — it diffs in git, so each poll's commit
  is a versioned snapshot. Don't swap the storage format without preserving
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
- **`test_e2e.py` deletes and overwrites `data/history.csv` and
  `data/alert_state.json` directly, in place, no confirmation.** Running it
  locally clobbers real committed data in the working tree (not just a
  copy) — restore both with `git checkout -- data/history.csv
  data/alert_state.json` immediately after, before touching real data or
  committing anything else.
