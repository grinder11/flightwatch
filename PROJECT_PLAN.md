# Japan 2027 — project plan

**Trip.** SFO out Fri 14 May 2027, back Sun 23 May. Four people. Open jaw into
HND, out of KIX. Six PTO days, exactly at your cap.

**Today.** 8 Sep 2026. 248 days out. You are in Phase 1 and slightly late on
one thing.

---

## The one time-sensitive item

Award inventory for May 2027 opened around **mid-June 2026**. It has been
bookable for roughly three months and premium-cabin space on SFO–Tokyo goes
first. If anyone in the group is sitting on transferable points — Amex MR,
Chase UR, Capital One — that audit should happen this week, not after the
tracker has a month of history. Cash fares get cheaper as you approach; award
seats only get scarcer.

This is independent of flightwatch and doesn't need your home setup.

---

## Phase 1 — Flight lock (now → February 2027)

### 1a. Away from your desk (this week, no setup needed)

- Award audit: point balances across all four people, and whether ANA/JAL
  fuel surcharges make the award worse than cash.
- Lock the group. Four people is only four people until someone's plans move.
  Get a verbal yes on the exact dates and a soft deposit if you can.
- Put in the PTO request. Six days in May, asked for in September, is
  uncontroversial. Asked for in March it competes with everyone else.
- Decide the 7th-day question now, in principle: if the Monday 24 May return
  comes in materially cheaper *and* buys a full extra day, would you ask for
  it? Deciding this cold is better than deciding it while an alert is
  blinking.

### 1b. At your desk (one evening, ~40 minutes)

1. Push the fixed files to a **private** repo.
2. Amadeus Self-Service app → `AMADEUS_KEY`, `AMADEUS_SECRET`.
3. BotFather → `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`.
4. Actions → Run workflow, by hand. Confirm six rows land in
   `data/history.csv`.
5. `python analyze.py` locally to confirm it reads back.

Before that evening, you can still run `test_logic.py`, `test_e2e.py`, and
`tracker.py --replay` on any laptop. They need no keys.

### 1c. Calibration (30 days after first run — roughly mid-October)

The $900 floor and the $1,500 ceiling are guesses from general knowledge of
the route, not from your data. After 30 observations per pairing:

- Read the real p20 off `analyze.py`.
- Set `book_now_usd` to roughly your observed p20, not to $900 if $900 never
  appears.
- Run `tracker.py --replay data/history.csv` after each threshold change to
  see how many alerts the new setting *would* have produced. Tune until it's
  one or two a week, not one a day.

### 1d. Buy window (December 2026 → February 2027)

Target Jan–Feb, with Travel Tuesday (1 Dec 2026) worth watching. Rule for
yourself, written down before you're emotional about it: **take anything at or
below your recalibrated floor on the target pairing, same day, without
consulting the group chat.** Group consensus is how good fares expire.

Keep the native Google Flights alerts on the same 4 pairings throughout.
They're the backstop for the week this returns zero offers and you don't
notice.

**Exit condition for Phase 1:** four tickets bought.

---

## Phase 2 — Domain and site (December 2026, or any weekend you want a break)

The page is built and in `docs/`. It reads `docs/data.json`, which the workflow
regenerates on every run. It renders with sample state before any data exists,
so you can look at it today.

**Hosting, and one thing to get right.** GitHub Pages on a *private* repo
requires a paid plan. You want the repo private — it holds your travel dates
and price history. Three ways out:

| Option | Cost | Note |
|---|---|---|
| Cloudflare Pages, private repo | free | connects to private GitHub repos on the free plan; this is the one to take |
| GitHub Pro + Pages | $4/mo | simplest, but you're paying for one page |
| Public repo | free | fine if you don't mind four people's travel dates being public |

**Domain.** Porkbun or Cloudflare Registrar. A `.xyz` or `.me` runs about
$5–12 for the first year; Cloudflare sells at wholesale with no renewal
markup, which matters more than the first-year price. Something short you'd
type on a phone — the whole point is opening it from a Telegram alert. Point
it at Cloudflare Pages, HTTPS is automatic.

Optional once the page is live: add a build step that also renders a
group-facing version with no dollar-thresholds visible, so you can share a
link without broadcasting your maximum.

**Exit condition:** you can open one URL on your phone and know whether to
buy.

---

## Phase 3 — Everything downstream (after tickets)

Order matters; each one gets cheaper or easier once the flights are fixed.

| When | What |
|---|---|
| Feb–Mar 2027 | Hotels. Tokyo 4 nights, Kyoto 2, Osaka 1. Free-cancellation rates, book early, re-check in April. |
| Apr 2027 | Sumo. Natsu basho runs mid-May at Ryōgoku; a weekday masu-seki box seats exactly four. Tickets go on sale roughly a month ahead and the good boxes move fast. Confirm the 2027 dates when the schedule publishes. |
| Apr 2027 | Shinkansen point-to-point via Smart EX. Skip the JR Pass — your routing doesn't earn it back. |
| Apr 2027 | eSIMs, four individual, not shared wifi. |
| May 2027 | Yamato luggage forwarding between hotels, arranged at the front desk. |

---

## What could still break this

- **Amadeus test-environment prices drift from reality.** Good for trend, wrong
  on the absolute number. Never buy off this page without checking Google
  Flights. Move to production keys once you trust the pipeline.
- **A silent zero-offer week.** Now alerts you when every route fails, but a
  *partially* broken run — one route quietly returning nothing — still just
  logs a warning. Skim the Actions tab monthly.
- **Scheduled workflows get disabled after 60 days of repo inactivity.** The
  daily history commit prevents this. If you ever pause the cron, it won't
  restart itself.
- **The group.** The most likely reason this trip changes shape is a person,
  not a fare. Phase 1a is the highest-leverage thing on this page.
