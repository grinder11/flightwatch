# flightwatch

Daily fare polling with append-only price history and statistical triggers.
Built for SFO to Japan, out Fri 14 May 2027, back Sun 23 May, six pairings.

Runs free on GitHub Actions. No server, no database.

See `VALIDATION.md` for what was tested and what was broken.

---

## Why this exists

Google Flights alerts tell you a price *changed*. They don't tell you whether
$1,150 is good, because they show you no history. This does three things the
free alerts can't:

1. Keeps a permanent record, so you can judge a number against its own past.
2. Fires on percentiles instead of vibes.
3. Watches six pairings at once, with the PTO cost of each attached, so a
   cheap adjacent day can't hide and an expensive one can't tempt you into
   a seventh day off without showing you the price.

---

## Setup

### 1. Repo

```bash
git init flightwatch && cd flightwatch
# drop these files in
git add . && git commit -m "init" && git push
```

Make it **private**. The history is yours and the config has your dates.
(If you want the site on GitHub Pages, see the hosting note in
`PROJECT_PLAN.md` — Pages on a private repo needs a paid plan.)

### 2. API credentials

**Amadeus is dead.** Its self-service portal was decommissioned on
2026-07-17 and all keys are disabled. It is not usable and not the
default — ignore any old instructions telling you to register for it.

**SerpApi (default, only working provider):** matches the Google Flights
UI. ~100 free searches/month; 5 routes daily would exhaust that in ~20
days, so the workflow polls every other day (`cron: "10 14 */2 * *"`) to
stay under the free tier. `provider: serpapi` in `config.yaml`.

### 3. Telegram alerts

1. Message `@BotFather`, send `/newbot`, copy the token.
2. Send your new bot any message.
3. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates`, copy
   `result[0].message.chat.id`.

### 4. GitHub secrets

Settings → Secrets and variables → Actions:

| Secret | Needed for |
|---|---|
| `SERPAPI_KEY` | SerpApi provider |
| `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` | alerts |

Then Actions → flightwatch → **Run workflow** for the first run.

---

## Files

```
config.yaml                  routes + alert rules            <- edit this
providers.py                 SerpApi adapter (Amadeus dead since 2026-07-17)
tracker.py                   poll -> append -> evaluate -> alert
analyze.py                   history report, CLI, site JSON
test_logic.py                trigger assertions, no keys needed
test_e2e.py                  45-day simulation, no keys needed
docs/index.html              the page
docs/data.json               written each run, read by the page
data/history.csv             append-only observations        <- your asset
data/alert_state.json        debounce bookkeeping
.github/workflows/track.yml  every-other-day cron
```

CSV rather than SQLite on purpose: it diffs in git, so every daily commit is a
versioned snapshot.

---

## Trigger rules

Evaluated in order, first match wins per route per run:

| Rule | Fires when |
|---|---|
| `FLOOR` | price ≤ `book_now_usd` ($900). Ignores history. Book on sight. |
| `NEW_LOW` | lowest in 30 days, with at least 8 observations in that window |
| `PERCENTILE` | below the 20th percentile of the last 60 days |
| `DROP` | ≥12% below the 7-day median |

Guards:

- Nothing above `ignore_above_usd` ($1,500) alerts except `FLOOR`.
- Statistical rules stay disarmed until `min_observations` (12) exist for the
  route, **and** until the specific window holds `min_obs_in_window` (8).
- Cooldown is per route, not per rule: 48h unless the price falls a further
  5%. Keying it per rule let NEW_LOW and PERCENTILE alternate down a decline
  and alert most days.
- Hard cap of 6 non-FLOOR alerts per route per 30 days.
- If every route returns zero offers, it alerts you that it's blind rather
  than exiting quietly.

Tune `book_now_usd` once you have a month of data, then use
`tracker.py --replay` to see how many alerts the new threshold would have
produced.

---

## Daily use

You don't. It messages you. When an alert fires:

```bash
git pull
python analyze.py                            # where does this sit?
python analyze.py --chart fri14_sun23_hnd_kix
```

Or open the page, which says the same thing in one sentence.

---

## Testing without credentials

All three run offline, no keys:

```bash
python test_logic.py                      # 14 assertions on the rules
python test_e2e.py                        # 45 simulated days x 6 routes
python tracker.py --replay data/history.csv   # re-score stored history
```

`--replay` is the threshold-tuning tool. Change a number in `config.yaml`,
re-run it, see what would have fired.

---

## Rough calibration, SFO to Tokyo, May

Starting thresholds, before your own data exists:

| Price | Read |
|---|---|
| < $900 | book immediately |
| $900–1,100 | good fare |
| $1,100–1,400 | normal |
| > $1,500 | wait |

Replace with your observed p20 after ~30 days.

---

## Failure modes

**Zero offers returned.** Usually a changed API response shape. Print the raw
payload first. A total failure now pings you; a single-route failure only
prints a warning, so skim the Actions tab monthly.

**Action stops running.** GitHub disables scheduled workflows after 60 days of
repo inactivity. The every-other-day commit prevents this.

**Cron runs late.** 10–30 minutes is normal and irrelevant here.

---

## Worth saying plainly

Keep the native Google Flights alerts on alongside this. They cost nothing,
they won't break when an API changes shape, and they're the backstop for the
week this silently returns zero offers. What you're buying here is the history
and the percentile judgment — not a replacement for a working free alert.

---

## Extending

- **More pairings:** add to `routes:`. Cost is linear in API quota.
- **Price for 4:** set `adults: 4`, but keep tracking `adults: 1` in parallel.
  Group searches return worse fares when fewer than 4 seats remain in the
  cheap bucket.
- **Hotels:** the same append-CSV + percentile pattern works unchanged. Swap
  the provider adapter.
