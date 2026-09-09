# Validation report

Everything below was run offline in a container against synthetic history.
No API keys, no network calls to Amadeus or SerpApi. You can reproduce all of
it on a laptop with `pip install pyyaml requests` and no credentials:

```bash
python test_logic.py                     # 14 assertions on the trigger rules
python test_e2e.py                       # 45 simulated days x 6 routes
python tracker.py --replay data/history.csv
```

---

## Blockers found

**1. Amadeus POST was missing a required header.** The multi-city form of
Flight Offers Search is rejected without `X-HTTP-Method-Override: GET`. The
default provider would have errored on every route, every run. Fixed in
`providers.py`, and the adapter now raises with the response body attached
instead of a bare status code.

**2. SerpApi crashed on every offer.** The carrier line read
`sorted({...}) - {""}` — a list minus a set, which is a `TypeError` in Python.
Reproduced in isolation:

```
BUG: TypeError unsupported operand type(s) for -: 'list' and 'set'
```

Not "returns nothing occasionally." The SerpApi path could never have
returned a single offer. Fixed.

Between these two, neither provider worked. "Full working project" was wrong,
and so was "verified in testing" in the README — nothing had been executed.

**3. The trip you're taking wasn't being tracked.** `config.yaml` had six
pairings; none of them was 14 May → 23 May. The set was built around the
earlier 5/13–5/22–5/24 exploration and never re-centred.

**4. Five of six pairings broke your PTO cap.** Weekdays consumed, computed
from the calendar:

| Pairing | Out | Back | PTO | vs cap of 6 |
|---|---|---|---|---|
| thu13_sat22 | Thu 05-13 | Sat 05-22 | 7 | over |
| thu13_mon24 | Thu 05-13 | Mon 05-24 | 8 | over |
| fri14_sat22 | Fri 05-14 | Sat 05-22 | 6 | ok |
| fri14_mon24 | Fri 05-14 | Mon 05-24 | 7 | over |
| thu13_sat22_nrt | Thu 05-13 | Sat 05-22 | 7 | over |
| thu13_sat22_rt | Thu 05-13 | Sat 05-22 | 7 | over |

Only one tracked pairing was actually bookable under your constraint.

---

## Logic defects found

**5. "Lowest in 30 days" could fire against a sample of one.**
`min_observations: 12` counts *all* history for a route. The window rules then
run on whatever happens to fall inside 30 or 60 days. A route with 40 rows
from three months ago and one row from last week reports "lowest in 30d"
against that single row. Added `min_obs_in_window: 8`.

**6. Alert fatigue, measured.** The cooldown keyed on `route + rule`, so
`NEW_LOW` and `PERCENTILE` alternated down a declining price, each with its
own untouched 48-hour timer.

| | old | fixed |
|---|---|---|
| Notification days, 45-day 6-route sim | 29 | 15 |
| Alerts, 90-day single-route sim | 27 | 17 (10 of them FLOOR) |

Cooldown is now keyed on the route. Added
`max_alerts_per_route_per_month: 6`, with FLOOR exempt so a sub-$900 fare
always gets through.

**7. `max_stops` summed stops across both directions.** One connection each
way scored as 2, so `max_stops: 1` would have rejected a normal one-stop
itinerary. Now the worst single direction.

**8. A manual "Run workflow" on a cron day silently double-logged.** Two rows
for one day inflate `n` and skew every percentile. Added a same-day guard,
overridable with `--force`.

**9. Total blindness was silent.** If every route returned zero offers — the
exact failure the README warned about — the run printed a warning to a log
nobody reads and exited clean. Now it sends you an alert saying it's blind.

**10. `duration_min` was never populated by Amadeus.** Hardcoded `None`. 91 of
270 cells blank in the simulation. Now parsed from the ISO `PT14H15M` field.

**11. Smaller ones.** A hand-edited naive timestamp in the CSV crashed every
comparison; corrupt CSV lines killed the whole run; a Telegram Markdown parse
error returned 400 and dropped the alert silently; `git push` in the workflow
had no rebase, so a manual dispatch racing the cron would fail the job.

---

## What was already correct

Confirmed by test, not by reading:

- The `min_observations` gate does hold. At 11 observations a would-be new low
  produces nothing; at 12 it arms.
- FLOOR fires with empty history, and the ceiling suppresses everything else
  above $1,500.
- Rule precedence is first-match, in the documented order.
- Route isolation is real — another route's history can't contaminate a
  percentile.
- The 5% cooldown override triggers at exactly 5%, not just beyond it.
- `percentile()` does correct linear interpolation: p20 of 1..100 is 20.8.
- CSV round-trip is lossless. 45 days × 6 routes wrote exactly 270 rows and
  read back clean.
