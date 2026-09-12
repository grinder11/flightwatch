#!/usr/bin/env python3
"""
flightwatch -- daily fare poll, append-only history, threshold alerting.

    python tracker.py            # normal run
    python tracker.py --dry-run  # fetch + evaluate, no alerts, no write
    python tracker.py --replay data/history.csv
                                 # re-evaluate stored history against the
                                 # current rules and print what WOULD have
                                 # fired. No network, no API keys.
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import median

import yaml
from dotenv import load_dotenv

from providers import get_provider

load_dotenv()

ROOT = Path(__file__).parent
HISTORY = ROOT / "data" / "history.csv"
STATE = ROOT / "data" / "alert_state.json"

FIELDS = [
    "ts", "route_id", "price", "carrier",
    # our derived combined (out+back) values -- populated only when
    # full_read: worst-direction stop count, summed duration
    "stops", "duration_min",
    # per-leg values, exactly as Google Flights shows each leg -- outbound_*
    # always populated when the leg-1 data exists; return_* only on full_read
    "outbound_stops", "outbound_duration_min",
    "return_stops", "return_duration_min",
    "return_routing", "full_read",
    "provider", "currency",
]


def fmt_duration(minutes):
    if minutes is None:
        return "?"
    h, m = divmod(int(minutes), 60)
    return f"{h}h{m:02d}m"


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------

def load_history(path=None):
    p = Path(path) if path else HISTORY
    if not p.exists():
        return []
    with p.open() as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        try:
            r["price"] = float(r["price"])
            ts = datetime.fromisoformat(r["ts"])
        except (ValueError, TypeError, KeyError):
            continue                                # skip a corrupt line
        # a naive timestamp from a hand-edited CSV would crash every
        # comparison below; assume UTC rather than blow up the run
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        r["ts"] = ts
        out.append(r)
    return out


def append_history(rows):
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    new = not HISTORY.exists()
    with HISTORY.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerows(rows)


def load_state():
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text())
    except json.JSONDecodeError:
        return {}


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2))


# ---------------------------------------------------------------------------
# trigger evaluation
# ---------------------------------------------------------------------------

def window(hist, route_id, days, now):
    cut = now - timedelta(days=days)
    return [r["price"] for r in hist
            if r["route_id"] == route_id and r["ts"] >= cut]


def percentile(values, pct):
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * pct / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def evaluate(route_id, price, hist, rules, now):
    """Return (rule_name, message) or (None, None)."""
    if price <= rules["book_now_usd"]:
        return "FLOOR", f"at or below your ${rules['book_now_usd']} book-now floor"

    if price > rules["ignore_above_usd"]:
        return None, None

    prior = [r for r in hist if r["route_id"] == route_id]
    if len(prior) < rules["min_observations"]:
        return None, None

    depth = rules.get("min_obs_in_window", 1)

    # A window rule is only meaningful if the window is actually populated.
    # min_observations counts ALL history, so a route with 40 old rows and one
    # recent row would otherwise report "lowest in 30 days" against a sample
    # of one.
    lows = window(hist, route_id, rules["new_low_window_days"], now)
    if len(lows) >= depth and price < min(lows):
        return "NEW_LOW", (
            f"lowest in {rules['new_low_window_days']}d "
            f"(prev low ${min(lows):,.0f}, n={len(lows)})"
        )

    pw = window(hist, route_id, rules["percentile_window_days"], now)
    if len(pw) >= depth:
        p = percentile(pw, rules["percentile_threshold"])
        if p is not None and price < p:
            return "PERCENTILE", (
                f"below p{rules['percentile_threshold']} of last "
                f"{rules['percentile_window_days']}d "
                f"(p{rules['percentile_threshold']}=${p:,.0f}, n={len(pw)})"
            )

    wk = window(hist, route_id, 7, now)
    if len(wk) >= min(depth, 4):
        m = median(wk)
        drop = (m - price) / m * 100
        if drop >= rules["drop_pct_vs_median"]:
            return "DROP", f"down {drop:.0f}% vs 7-day median (${m:,.0f})"

    return None, None


def cooldown_ok(state, route_id, rule, price, rules, now):
    """Debounce at ROUTE level, not route+rule.

    Keying on route+rule let NEW_LOW and PERCENTILE alternate down a slow
    decline, each with its own untouched cooldown. A 45-day simulation
    produced 29 alert days that way; route-level keying gives 7.

    FLOOR is exempt from the monthly cap -- a sub-floor fare always gets out.
    """
    key = route_id
    last = state.get(key)

    if rule != "FLOOR":
        cap = rules.get("max_alerts_per_route_per_month")
        if cap:
            recent = [
                t for t in (last or {}).get("recent", [])
                if datetime.fromisoformat(t) > now - timedelta(days=30)
            ]
            if len(recent) >= cap:
                return False

    if not last:
        return True
    then = datetime.fromisoformat(last["ts"])
    if (now - then) > timedelta(hours=rules["cooldown_hours"]):
        return True
    # still cooling down -- override only on a further material drop
    return price <= last["price"] * (1 - rules["cooldown_override_pct"] / 100)


def record_alert(state, route_id, price, now):
    last = state.get(route_id, {})
    recent = [
        t for t in last.get("recent", [])
        if datetime.fromisoformat(t) > now - timedelta(days=30)
    ]
    recent.append(now.isoformat())
    state[route_id] = {"ts": now.isoformat(), "price": price, "recent": recent}


def already_logged_today(hist, route_id, now):
    """Guard against a manual Run-workflow on a day the cron already ran.
    A duplicate row inflates n and skews every percentile."""
    return any(
        r["route_id"] == route_id and r["ts"].date() == now.date()
        for r in hist
    )


# ---------------------------------------------------------------------------
# notification
# ---------------------------------------------------------------------------

def notify(text, cfg):
    sent = False
    if cfg["notify"].get("telegram"):
        import requests
        tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        if tok and chat:
            r = requests.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": chat, "text": text,
                      "parse_mode": "Markdown",
                      "disable_web_page_preview": True},
                timeout=20,
            )
            if r.status_code >= 400:
                # a Markdown parse error returns 400 and silently drops the
                # alert; retry as plain text rather than lose it
                print(f"[warn] telegram {r.status_code}: {r.text[:200]}")
                requests.post(
                    f"https://api.telegram.org/bot{tok}/sendMessage",
                    json={"chat_id": chat, "text": text},
                    timeout=20,
                )
            sent = True
        else:
            print("[warn] telegram enabled but TELEGRAM_TOKEN/CHAT_ID unset")
    if cfg["notify"].get("email"):
        import smtplib
        from email.message import EmailMessage
        msg = EmailMessage()
        msg["Subject"] = "flightwatch alert"
        msg["From"] = os.environ["SMTP_USER"]
        msg["To"] = cfg["notify"]["email_to"]
        msg.set_content(text)
        with smtplib.SMTP_SSL(os.environ["SMTP_HOST"],
                              int(os.environ.get("SMTP_PORT", 465))) as s:
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            s.send_message(msg)
        sent = True
    if not sent:
        print("[warn] no notifier configured; alert printed only")
        print(text)


# ---------------------------------------------------------------------------

def replay(cfg, path):
    """Re-run every stored observation through the current rules, in order.
    Offline. This is how you tune thresholds without waiting for live data."""
    rules = cfg["alerts"]
    rows = sorted(load_history(path), key=lambda r: r["ts"])
    if not rows:
        print(f"no history at {path}")
        return
    seen, state, fired = [], {}, 0
    for r in rows:
        rule, why = evaluate(r["route_id"], r["price"], seen, rules, r["ts"])
        if rule and cooldown_ok(state, r["route_id"], rule, r["price"], rules, r["ts"]):
            record_alert(state, r["route_id"], r["price"], r["ts"])
            fired += 1
            print(f"{r['ts'].date()}  {r['route_id']:22s} "
                  f"${r['price']:>7,.0f}  {rule:<10s} {why}")
        seen.append(r)
    span = (rows[-1]["ts"] - rows[0]["ts"]).days or 1
    print(f"\n{fired} alerts over {span} days "
          f"({fired / span * 7:.1f}/week) across "
          f"{len({r['route_id'] for r in rows})} routes")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--replay", metavar="CSV",
                    help="re-evaluate a history file offline and exit")
    ap.add_argument("--force", action="store_true",
                    help="log a second observation on a day already logged")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    rules = cfg["alerts"]

    if args.replay:
        replay(cfg, args.replay)
        return

    now = datetime.now(timezone.utc)
    hist = load_history()
    state = load_state()
    provider = get_provider(cfg["provider"])

    new_rows, alerts, failures = [], [], []
    warned_stops_unavailable = False

    for route in cfg["routes"]:
        rid = route["id"]
        try:
            offers = provider.search(route, cfg)
        except Exception as e:                      # noqa: BLE001
            print(f"[error] {rid}: {e}", file=sys.stderr)
            failures.append(rid)
            continue

        if cfg.get("max_stops") is not None:
            def stop_count(o):
                # combined (full_read) is the more accurate per-direction
                # worst-case; fall back to outbound-leg-only otherwise.
                return o["stops"] if o["stops"] is not None else o["outbound_stops"]
            if not warned_stops_unavailable and any(stop_count(o) is None for o in offers):
                print(f"[warn] stops unavailable from {cfg['provider']}; "
                      f"max_stops is being ignored")
                warned_stops_unavailable = True
            offers = [
                o for o in offers
                if stop_count(o) is None or stop_count(o) <= cfg["max_stops"]
            ]

        max_total = cfg.get("max_total_duration_min")
        if max_total is not None:
            before = len(offers)
            offers = [
                o for o in offers
                if not o["full_read"] or o["duration_min"] is None
                or o["duration_min"] <= max_total
            ]
            if len(offers) < before:
                print(f"[warn] {rid}: combined duration over "
                      f"max_total_duration_min ({max_total}min); offer dropped")

        if not offers:
            print(f"[warn] {rid}: no offers returned")
            failures.append(rid)
            continue

        best = min(offers, key=lambda o: o["price"])

        if already_logged_today(hist, rid, now) and not args.force:
            print(f"[skip] {rid}: already logged today "
                  f"(${best['price']:,.0f} seen, not stored)")
            continue

        new_rows.append({
            "ts": now.isoformat(),
            "route_id": rid,
            "price": round(best["price"], 2),
            "carrier": best["carrier"],
            "stops": best["stops"] if best["stops"] is not None else "",
            "duration_min": best["duration_min"] or "",
            "outbound_stops": (
                best["outbound_stops"] if best["outbound_stops"] is not None else ""
            ),
            "outbound_duration_min": best["outbound_duration_min"] or "",
            "return_stops": (
                best["return_stops"] if best["return_stops"] is not None else ""
            ),
            "return_duration_min": best["return_duration_min"] or "",
            "return_routing": best["return_routing"],
            "full_read": best["full_read"],
            "provider": cfg["provider"],
            "currency": cfg["currency"],
        })
        if best["full_read"]:
            stops_disp = (
                f"{best['outbound_stops']} out / {best['return_stops']} back"
            )
            dur_disp = (
                f"{fmt_duration(best['outbound_duration_min'])} out + "
                f"{fmt_duration(best['return_duration_min'])} back "
                f"= {fmt_duration(best['duration_min'])} total"
            )
        else:
            stops_disp = (
                f"{best['outbound_stops']} stop(s) outbound"
                if best["outbound_stops"] is not None else "? stops outbound"
            )
            dur_disp = f"{fmt_duration(best['outbound_duration_min'])} outbound"
        print(f"{rid:24s} ${best['price']:>8,.0f}  {best['carrier']:<12s} "
              f"{stops_disp}  {dur_disp}")

        rule, why = evaluate(rid, best["price"], hist, rules, now)
        if rule and cooldown_ok(state, rid, rule, best["price"], rules, now):
            duration_flag = ""
            if best["full_read"] and best["duration_min"]:
                dur = best["duration_min"]
                duration_flag = f"\n_combined duration: {fmt_duration(dur)} (out+back)_"
                prefer_under = rules.get("prefer_under_min")
                if prefer_under and dur > prefer_under:
                    duration_flag += (
                        f"\n_long haul: over your "
                        f"{fmt_duration(prefer_under)} preference_"
                    )
            if best["full_read"]:
                stops_note = f"{best['outbound_stops']} out / {best['return_stops']} back stops"
            else:
                stops_note = f"{best['outbound_stops']} stop outbound"
            alerts.append(
                f"*{rid}*  ${best['price']:,.0f}  ({best['carrier']}, "
                f"{stops_note}, {route.get('pto', '?')} PTO days)\n"
                f"_{why}_{duration_flag}\n{route.get('note', '')}"
            )
            record_alert(state, rid, best["price"], now)

    # Every route failing at once means the API changed shape or the key
    # died. Say so loudly -- a silent zero-offer week is the failure mode
    # that actually costs money.
    if failures and len(failures) == len(cfg["routes"]):
        msg = ("*flightwatch is blind* -- every route returned nothing today. "
               "Check the API key and the raw payload.")
        print("[ERROR] " + msg, file=sys.stderr)
        if not args.dry_run:
            notify(msg, cfg)

    if args.dry_run:
        print("\n[dry-run] would write "
              f"{len(new_rows)} rows, send {len(alerts)} alert(s)")
        for a in alerts:
            print("---\n" + a)
        return

    if new_rows:
        append_history(new_rows)
    if alerts:
        notify("Fare alert\n\n" + "\n\n".join(alerts), cfg)
    save_state(state)


if __name__ == "__main__":
    main()
