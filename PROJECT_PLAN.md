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

The site is built and in `docs/`, with three tabs — Flights (`data.json`, from
the history), Itinerary (`itinerary.json`, from `itinerary.yaml`), and Plans
(empty until there's a `plans.yaml`). The workflow regenerates all of them on
every run. Every tab renders an empty state before its data exists.

**Hosting is already settled: GitHub Pages, and nothing needs to change.** The
repo is public, so Pages is free *including* a custom domain and automatic
HTTPS — the earlier plan here recommended Cloudflare Pages only because a
*private* repo would have needed a paid GitHub plan. That no longer applies.
Cloudflare is worth revisiting only if the repo goes private again.

Confirmed working: the poller's own commit already triggers a Pages rebuild
(build history shows a `github-actions[bot]` push deploying clean), so the site
is current within a minute of every run. Actions writes, Pages serves; the two
only meet at a commit.

**Domain.** Porkbun or Cloudflare Registrar — Cloudflare sells at wholesale
with no renewal markup, which matters more than the first-year price. Something
short you'd type on a phone; the whole point is opening it from a Telegram
alert. Then:

1. Settings → Pages → Custom domain. GitHub commits a `CNAME` file — check it
   lands in `docs/`, the publishing source, not the repo root.
2. DNS: apex needs four A records (`185.199.108–111.153`) plus four AAAA
   (`2606:50c0:800{0,1,2,3}::153`); a `www` subdomain needs one CNAME to
   `grinder11.github.io`. No wildcard records.
3. Wait for the certificate, then tick **Enforce HTTPS**.

If Cloudflare is the registrar, that's fine — but leave those records **DNS
only** (grey cloud). Proxying blocks GitHub's cert issuance, and "Flexible" SSL
in front of an HTTPS-enforced Pages site gives a redirect loop.

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
