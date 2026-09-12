# flightwatch

An every-other-day fare-polling tool for a trip: SFO to Japan, open jaw into
HND, out of KIX. It watches several date/routing variants of that trip at
once (defined in `config.yaml`), keeps a permanent price history, and
alerts on statistical triggers instead of raw price change.

Google Flights' own price-drop alerts tell you a number *changed*. They
don't tell you whether it's actually good, because they show no history.
This does three things those alerts can't:

1. Keeps a permanent, append-only record, so a price gets judged against
   its own past instead of vibes.
2. Fires on percentiles and new-lows, not on "it moved."
3. Watches every tracked date/routing variant at once, each with its PTO
   cost attached, so a cheap adjacent date can't hide and an expensive one
   can't tempt a decision without showing the real number.

Runs free, no server, no database.

---

## How it works

```
config.yaml  --  routes + alert thresholds (the file to edit)
     |
     v
providers.py --  fetches fares (SerpApi, scraping Google Flights)
     |
     v
tracker.py   --  poll -> append to data/history.csv -> evaluate alert
     |            rules -> notify via Telegram
     v
analyze.py   --  reads history.csv, writes docs/data.json
     |
     v
docs/        --  static site reading data.json
```

`data/history.csv` is append-only and lives in git on purpose: every
scheduled run's commit is a versioned snapshot of that day's fares, and the
file diffs cleanly, which a database wouldn't.

A GitHub Actions workflow (`.github/workflows/track.yml`) runs `tracker.py`
on a cron, then `analyze.py --json`, then commits the results. GitHub
Actions runs this specifically because it can `git commit` its own output
directly — the storage design depends on that. The read-only site is served
by GitHub Pages from `main:/docs`, live at
https://grinder11.github.io/flightwatch/ (`PROJECT_PLAN.md` weighs the
Cloudflare Pages alternative, which was not taken).

## Fare data: SerpApi

SerpApi scrapes Google Flights, so its numbers match what the browser
shows. It's the only working provider — Amadeus's self-service portal was
decommissioned 2026-07-17 and all keys are dead; that adapter is kept in
`providers.py` purely as inert reference code.

Each plain route costs 1 SerpApi request per poll. Routes with
`full_read: true` cost 2 — SerpApi's multi-city search only exposes the
outbound leg on the first request, so `full_read` routes make a second
`departure_token` follow-up to confirm the real return leg's stops and
duration rather than trusting the outbound-only view. The free tier is
~100 searches/month; the cron's cadence and the current route mix's total
requests/poll are worth checking against that in `config.yaml`'s comments
before changing either.

## Credentials

The workflow needs these as GitHub Actions repo secrets (Settings → Secrets
and variables → Actions):

| Secret | Needed for |
|---|---|
| `SERPAPI_KEY` | fare data (serpapi.com) |
| `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` | alert delivery, from a bot registered with `@BotFather` |

Locally, the same values go in a gitignored `.env`; `tracker.py` loads it
via `python-dotenv` (a no-op in CI, which gets its values from the secrets
above instead).

## Alert rules

Evaluated in order, first match wins per route per run:

| Rule | Fires when |
|---|---|
| `FLOOR` | price ≤ `book_now_usd`. Ignores history and the ceiling. Book on sight. |
| `NEW_LOW` | lowest in `new_low_window_days`, once that window has enough observations |
| `PERCENTILE` | below the configured percentile of the recent window |
| `DROP` | down by the configured percentage vs. the 7-day median |

Guards:

- Nothing above `ignore_above_usd` alerts except `FLOOR`.
- Statistical rules stay disarmed until `min_observations` exist for the
  route overall, **and** until the specific window holds `min_obs_in_window`
  — otherwise a route with old history plus one recent row could report a
  false "lowest in 30 days" against a sample of one.
- Cooldown is per route, not per rule, so a slow decline can't alternate
  between two rules and alert almost daily. A material further drop
  (`cooldown_override_pct`) still overrides the cooldown.
- A hard cap limits non-`FLOOR` alerts per route per month.
- If every route returns zero offers in one run, it alerts that it's blind
  rather than exiting quietly; a single route failing just warns.

`tracker.py --replay data/history.csv` re-scores stored history against
whatever's currently in `config.yaml` — the way to see what a threshold
change would have fired, without waiting on new data.

## Files

```
config.yaml                  routes + alert rules            <- edit this
providers.py                 SerpApi adapter (Amadeus dead since 2026-07-17)
tracker.py                   poll -> append -> evaluate -> alert
analyze.py                   history report, CLI, site JSON
test_logic.py                trigger assertions, no keys needed
test_e2e.py                  multi-day simulation, no keys needed
docs/index.html              the page
docs/data.json               written each run, read by the page
data/history.csv             append-only observations        <- the actual asset
data/alert_state.json        debounce bookkeeping
.github/workflows/track.yml  cron: poll, analyze, commit
```

## Using it

Day to day, you don't touch it — it messages you on Telegram when a fare
clears a threshold. To look at the data directly:

```bash
python analyze.py                            # every route, one line each
python analyze.py --chart fri14_sun23_hnd_kix
```

Or open the site, which says the same thing in one sentence per route.

## Testing

All three run fully offline, no API keys, no network:

```bash
python test_logic.py                          # assertions on the trigger rules
python test_e2e.py                            # multi-day, multi-route simulation
python tracker.py --replay data/history.csv   # re-score stored history
```

## Known limitations

- SerpApi's returned offer list can be incomplete relative to what Google's
  own live UI shows for the identical search — confirmed empirically, see
  `CLAUDE.md`. There's no fix on our end short of a different data source;
  "cheapest offer we got" isn't provably "cheapest offer that exists."
- A zero-offer run is usually SerpApi's response shape having changed —
  print the raw payload before debugging anything else.
- GitHub disables a scheduled workflow after 60 days of repo inactivity;
  the cron's own commits keep the repo active.
- Keep the native Google Flights price-drop alerts on regardless. They cost
  nothing, won't break when an API changes shape, and are the backstop for
  the week this silently returns zero offers. This tool is the history and
  percentile layer on top, not a replacement for a working free alert.

See `CLAUDE.md` for the full list of constraints and past bugs that matter
for future changes, and `VALIDATION.md` for the historical build-time test
report.

## Extending

- **More routes:** add to `routes:` in `config.yaml`. Cost is linear in
  SerpApi quota; `full_read`/`nonstop` routes cost double.
- **Price for a group:** set `adults` above 1, but keep a parallel
  single-adult route too — group searches can return worse fares once the
  cheap fare bucket has fewer seats left than the party size.
- **A different trip entirely:** the append-CSV + percentile pattern isn't
  specific to flights. Swap the provider adapter and the rest holds.
