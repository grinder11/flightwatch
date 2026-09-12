#!/usr/bin/env python3
"""
Read the accumulated history and tell you whether a number is actually good.

    python analyze.py              # summary of every route
    python analyze.py --days 90    # restrict window
    python analyze.py --chart fri14_sun23_hnd_kix
    python analyze.py --json       # write docs/data.json for the site
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import median, mean

import yaml

from tracker import load_history, percentile

ROOT = Path(__file__).parent
BLOCKS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"


def sparkline(values):
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    if hi == lo:
        return BLOCKS[0] * len(values)
    return "".join(
        BLOCKS[int((v - lo) / (hi - lo) * (len(BLOCKS) - 1))] for v in values
    )


def verdict(price, prices):
    """Where does this price sit in its own history?"""
    if len(prices) < 5:
        return f"only {len(prices)} obs -- no verdict yet"
    p20 = percentile(prices, 20)
    p50 = percentile(prices, 50)
    if price <= min(prices):
        return "BEST EVER SEEN -- book it"
    if price <= p20:
        return "bottom quintile -- strong"
    if price <= p50:
        return "below median -- decent"
    return "above median -- wait"


def daily_lows(rows):
    """Collapse to one point per calendar day, so a manual re-run doesn't
    double-weight a day in the chart."""
    d = defaultdict(list)
    for r in rows:
        d[r["ts"].date()].append(r["price"])
    return [(day, min(d[day])) for day in sorted(d)]


def _int(v):
    """CSV fields land as strings, '' when the source column was blank."""
    return int(v) if v not in (None, "") else None


def build_payload(by_route, cfg):
    notes = {r["id"]: r for r in cfg.get("routes", [])}
    rules = cfg.get("alerts", {})
    out = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "floor": rules.get("book_now_usd"),
        "ceiling": rules.get("ignore_above_usd"),
        "routes": [],
    }
    for rid in sorted(by_route):
        rows = sorted(by_route[rid], key=lambda r: r["ts"])
        prices = [r["price"] for r in rows]
        series = daily_lows(rows)
        meta = notes.get(rid, {})
        out["routes"].append({
            "id": rid,
            "note": (meta.get("note") or "").strip(),
            "target": bool(meta.get("target")),
            "role": meta.get("role", "candidate"),
            "nonstop": bool(meta.get("nonstop")),
            "pto": meta.get("pto"),
            "depart": str(meta.get("depart", "")),
            "back": str(meta.get("return", "")),
            "path": f"{meta.get('origin','')}\u2192{meta.get('destination','')}"
                    f" / {meta.get('return_origin','')}\u2192"
                    f"{meta.get('return_destination','')}",
            "n": len(prices),
            "now": prices[-1],
            "min": min(prices),
            "p20": percentile(prices, 20),
            "median": median(prices),
            "max": max(prices),
            "carrier": rows[-1].get("carrier", ""),
            "stops": _int(rows[-1].get("stops")),
            "duration_min": _int(rows[-1].get("duration_min")),
            "full_read": rows[-1].get("full_read") == "True",
            "outbound_stops": _int(rows[-1].get("outbound_stops")),
            "outbound_duration_min": _int(rows[-1].get("outbound_duration_min")),
            "outbound_depart": rows[-1].get("outbound_depart") or "",
            "outbound_arrive": rows[-1].get("outbound_arrive") or "",
            "return_stops": _int(rows[-1].get("return_stops")),
            "return_duration_min": _int(rows[-1].get("return_duration_min")),
            "return_depart": rows[-1].get("return_depart") or "",
            "return_arrive": rows[-1].get("return_arrive") or "",
            "verdict": verdict(prices[-1], prices),
            "series": [{"d": str(d), "p": p} for d, p in series],
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--chart", help="route_id to print a daily-low series for")
    ap.add_argument("--json", action="store_true",
                    help="write the site payload and exit")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    hist = load_history()
    if not hist:
        print("No history yet. Run tracker.py first.")
        if args.json:
            dest = ROOT / cfg.get("site", {}).get("json_out", "docs/data.json")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(
                {"generated": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"), "routes": []}, indent=1))
        return

    cut = datetime.now(timezone.utc) - timedelta(days=args.days)
    hist = [r for r in hist if r["ts"] >= cut]

    by_route = defaultdict(list)
    for r in hist:
        by_route[r["route_id"]].append(r)

    if args.json:
        dest = ROOT / cfg.get("site", {}).get("json_out", "docs/data.json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(build_payload(by_route, cfg), indent=1))
        print(f"wrote {dest} ({len(by_route)} routes, {len(hist)} obs)")
        return

    if args.chart:
        rows = sorted(by_route.get(args.chart, []), key=lambda r: r["ts"])
        if not rows:
            print(f"No data for {args.chart}. Known routes: "
                  + ", ".join(sorted(by_route)))
            return
        series = daily_lows(rows)
        floor = min(p for _, p in series)
        print(f"\n{args.chart} -- daily low\n")
        for d, lo in series:
            print(f"  {d}  ${lo:>7,.0f}  {'#' * int((lo - floor) / 25 + 1)}")
        return

    ptos = {r["id"]: r.get("pto") for r in cfg.get("routes", [])}
    print(f"\n{'route':24s} {'PTO':>3s} {'n':>4s} {'now':>8s} {'min':>8s} "
          f"{'p20':>8s} {'med':>8s} {'max':>8s}  trend      verdict")
    print("-" * 110)

    for rid in sorted(by_route):
        rows = sorted(by_route[rid], key=lambda r: r["ts"])
        prices = [r["price"] for r in rows]
        now = prices[-1]
        spark = sparkline([p for _, p in daily_lows(rows)][-30:])
        print(
            f"{rid:24s} {str(ptos.get(rid, '?')):>3s} {len(prices):>4d} "
            f"${now:>7,.0f} ${min(prices):>7,.0f} "
            f"${percentile(prices, 20):>7,.0f} ${median(prices):>7,.0f} "
            f"${max(prices):>7,.0f}  {spark:<10s} {verdict(now, prices)}"
        )

    all_prices = [r["price"] for r in hist]
    print(f"\n{len(hist)} observations across {len(by_route)} routes, "
          f"mean ${mean(all_prices):,.0f}\n")


if __name__ == "__main__":
    main()
