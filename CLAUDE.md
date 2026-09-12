# flightwatch

Polls fares for one trip — SFO→Japan, out Fri 2027-05-14, back Sun 2027-05-23,
open jaw (HND in, KIX out) — on an every-other-day GitHub Actions cron, appends
to `data/history.csv`, and Telegram-alerts on statistical triggers rather than
raw price change. No server, no database.

`config.yaml` is the file to edit: routes and thresholds, with the live route
count and quota math in its own comments. `providers.py` fetches — **SerpApi
only; Amadeus decommissioned self-service 2026-07-17, keys are dead, that
adapter is inert reference code.** `tracker.py` polls → evaluates → alerts;
`analyze.py --json` writes every site payload (GitHub Pages serves `main:/docs`,
and the poller's own commit triggers the rebuild).

The site is three tabs sharing `docs/site.css` + `docs/site.js`: `index.html`
(Flights, from `data.json`), `itinerary.html` (from `itinerary.yaml` →
`itinerary.json`), `plans.html` (from `plans.yaml` → `plans.json`; absent by
design, so the tab renders an empty state). Each has its own `<tab>.js`.

## Commands — all offline, no keys

```bash
python test_logic.py                         # trigger-rule assertions
python test_e2e.py                           # 45-day sim; CLOBBERS data/, see below
python tracker.py --replay data/history.csv  # re-score history against current config
python analyze.py --json                     # rebuild every docs/*.json payload
cd docs && python -m http.server             # preview the site; file:// blocks its fetches
```

`--replay` is the tuning loop: change a threshold, rerun, see what would have
fired historically.

## Constraints

- **Route `id`s are permanent join keys** into `history.csv`. Renaming or
  reusing one for a different itinerary silently contaminates that route's
  percentile history.
- **`test_e2e.py` deletes and rewrites `data/history.csv` and
  `data/alert_state.json` in place** — real committed data in the working tree,
  not a copy. Run it in a scratch copy, or `git checkout -- data/` immediately
  after.
- **Schema changes to `FIELDS` need the migration exercised, not just the list
  edited.** `append_history()` calls `_migrate_history_header()` so a grown
  `FIELDS` rewrites the header and backfills old rows blank instead of
  appending misaligned columns. Verify: `git diff data/history.csv` shows
  header plus blank new columns only, no data altered.
- **CSV over SQLite is deliberate** — it diffs in git, so each poll's commit is
  a versioned snapshot. Preserve that property.
- **One observation per calendar day is a hard assumption.**
  `min_observations`, `min_obs_in_window` and every window size are row counts,
  not distinct days, so polling twice a day halves what each gate means.
  `daily_lows()` collapses duplicates for *display* only; the alert engine does
  not. Don't raise the frequency without redesigning the window logic.
- **Rules run in fixed order, first match wins per route per run:** FLOOR →
  NEW_LOW → PERCENTILE → DROP. FLOOR (≤ `book_now_usd`) ignores history *and*
  the `ignore_above_usd` ceiling — the one rule that always gets through.
- **Two depth gates:** `min_observations` across all history AND
  `min_obs_in_window` inside the window (the latter stops "lowest in 30 days"
  firing against a sample of one). DROP is the exception — hardcoded 7-day
  window, gate of `min(min_obs_in_window, 4)`.
- **Cooldown is keyed per route, not per route+rule** — per-rule let NEW_LOW and
  PERCENTILE alternate down a slow decline and alert almost daily
  (`VALIDATION.md` has the measurement). `max_alerts_per_route_per_month` is a
  hard cap; FLOOR is exempt from it, not from the cooldown.
- **Total blindness — every route returning zero offers — must alert.** A
  single-route failure only warns. Was a real bug.
- **Same-day guard:** a manual run on a day already polled logs nothing;
  `--force` overrides it and inflates `n`. A manual run on a *missed* day needs
  no flag.
- **`max_stops` counts per direction, never summed** across the round trip —
  matching Google's own filter, where each leg must independently pass.
- **Duration caps drop offers client-side, and a route left with zero offers is
  logged as a failure** — so a tightened cap reads as a provider outage.
  `max_outbound_duration_min` goes to SerpApi as `max_duration` (outbound
  only); `max_total_duration_min` is checked after the follow-up request, so it
  only applies to `full_read` routes. `prefer_under_min` drops nothing, it only
  annotates alert text.
- **SerpApi multi-city (`type=3`) request 1 sees the outbound leg only.** Its
  `price` is already the true round-trip total, but the return's
  stops/duration/routing stay invisible until you follow that offer's
  `departure_token`; the cheapest return there reproduces the quoted total.
  `full_read: true` makes that second request and populates real
  `stops`/`duration_min` (worst direction, summed) plus `return_*` fields;
  non-full-read routes get `outbound_*` only. **It doubles quota, and the
  current mix already exceeds the ~100/month free tier — check `config.yaml`
  before adding another `full_read`/`nonstop` route.**
- **SerpApi's offer list can omit options Google's live UI shows** (confirmed
  empirically; details in `providers.py`). Never claim "cheapest that exists,"
  only "cheapest we saw."
- **`target: true` / `role: baseline` drive the site's buckets and the "cheapest
  now" badge.** Anything that isn't a real option for this trip needs
  `role: baseline` or it pollutes "cheapest." There is no bucket for a plain
  candidate — `classify()` falls through to `lever`, i.e. "7-Day Variants"
  whatever its `pto` — so fix the buckets rather than mislabel a route.
- **PTO cap is 6 weekdays**, per route via `pto`. Over-cap routes are priced
  levers, not bookable candidates.
- **Nights per city and booking counts are derived** in `build_itinerary_payload()`
  from `itinerary.yaml`'s day list — never restate them in the YAML, or the file
  can disagree with itself. The dates give 8 nights, not the 7 that
  `PROJECT_PLAN.md` assumes; the spare one currently sits in Tokyo.
- **The cron's `*/2` is day-of-month parity**, not "2 days after last run," so a
  month boundary can give a 1- or 3-day gap.

## Local dev

- `source .venv/bin/activate` in every new shell — it isn't inherited.
- `SERPAPI_KEY`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` go in a gitignored
  `.env`, loaded at import time (a no-op in CI, which uses Actions secrets).
- Only real observations belong in `data/history.csv`.
