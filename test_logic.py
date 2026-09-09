"""Offline validation of tracker trigger logic. No network, no API keys."""
import random
from datetime import datetime, timezone, timedelta
import yaml
from tracker import evaluate, cooldown_ok, percentile, record_alert

cfg = yaml.safe_load(open("config.yaml").read())
rules = cfg["alerts"]
NOW = datetime(2027, 1, 15, tzinfo=timezone.utc)
RID = "fri14_sun23_hnd_kix"


def hist(prices, rid=RID, start_days_ago=None):
    n = len(prices)
    start = start_days_ago if start_days_ago is not None else n
    return [
        {"route_id": rid, "price": float(p), "ts": NOW - timedelta(days=start - i)}
        for i, p in enumerate(prices)
    ]


def check(name, got, want):
    flag = "PASS" if got == want else "**FAIL**"
    print(f"{flag:9s} {name}\n          got={got!r}\n          want={want!r}")


print("=" * 70)
print("A. Guard: statistical rules disarmed below min_observations (12)")
print("=" * 70)
h11 = hist([1200] * 11)
check("11 obs, price 1000 (a new low) -> no alert",
      evaluate(RID, 1000, h11, rules, NOW)[0], None)
h12 = hist([1200] * 12)
check("12 obs, price 1000 -> NEW_LOW arms",
      evaluate(RID, 1000, h12, rules, NOW)[0], "NEW_LOW")

print()
print("=" * 70)
print("B. Guard: min_observations counts ALL history, windows do not")
print("=" * 70)
old = hist([1200] * 20, start_days_ago=400)   # 20 obs, all >365d old
check("20 ancient obs, price 1000 -> arms on stale data",
      evaluate(RID, 1000, old, rules, NOW)[0], None)

print()
print("=" * 70)
print("C. Ceiling and floor")
print("=" * 70)
h = hist([1200] * 30)
check("price 899 (<= 900 floor) -> FLOOR", evaluate(RID, 899, h, rules, NOW)[0], "FLOOR")
check("price 1600 (> 1500 ceiling) -> suppressed",
      evaluate(RID, 1600, h, rules, NOW)[0], None)
check("price 899 with EMPTY history -> FLOOR still fires",
      evaluate(RID, 899, [], rules, NOW)[0], "FLOOR")

print()
print("=" * 70)
print("D. Rule precedence")
print("=" * 70)
h = hist([1200] * 30)
check("1000 vs flat 1200 history -> NEW_LOW wins over DROP",
      evaluate(RID, 1000, h, rules, NOW)[0], "NEW_LOW")
# price above 30d low but below p20 of 60d
h2 = hist([900, 950, 1000] + [1300] * 27, start_days_ago=59)
print("          p20(60d) =", percentile([r["price"] for r in h2], 20))
check("1150: above 30d low, below p20 -> PERCENTILE",
      evaluate(RID, 1150, h2, rules, NOW)[0], "PERCENTILE")

print()
print("=" * 70)
print("E. Route isolation (other routes must not contaminate)")
print("=" * 70)
mixed = hist([1200] * 12, rid="OTHER") + hist([1300] * 12)
check("12 obs on this route + 12 on another -> evaluates own route only",
      evaluate(RID, 1250, mixed, rules, NOW)[0], "NEW_LOW")

print()
print("=" * 70)
print("F. Cooldown / debounce")
print("=" * 70)
state = {RID: {"ts": (NOW - timedelta(hours=10)).isoformat(), "price": 1000.0, "recent": []}}
check("10h later, price 999 (0.1% lower) -> suppressed",
      cooldown_ok(state, RID, "NEW_LOW", 999, rules, NOW), False)
check("10h later, price 940 (6% lower) -> overrides",
      cooldown_ok(state, RID, "NEW_LOW", 940, rules, NOW), True)
check("10h later, price 950 (exactly 5% lower) -> overrides",
      cooldown_ok(state, RID, "NEW_LOW", 950, rules, NOW), True)
old_state = {RID: {"ts": (NOW - timedelta(hours=49)).isoformat(), "price": 1000.0, "recent": []}}
check("49h later (>48h), price 999 -> allowed",
      cooldown_ok(old_state, RID, "NEW_LOW", 999, rules, NOW), True)
check("no prior state -> allowed",
      cooldown_ok({}, RID, "NEW_LOW", 999, rules, NOW), True)

print()
print("=" * 70)
print("G. Percentile function sanity")
print("=" * 70)
vals = list(range(1, 101))
print("          p20 of 1..100 =", percentile(vals, 20), "(expect 20.8, linear interp)")
print("          p50 of 1..100 =", percentile(vals, 50))
print("          empty ->", percentile([], 20))
print("          single value ->", percentile([1000], 20))

print()
print("=" * 70)
print("H. Realistic 90-day simulation: how often does it actually fire?")
print("=" * 70)
random.seed(7)
h, fires = [], []
price = 1350.0
st = {}
for day in range(90):
    ts = NOW - timedelta(days=90 - day)
    price = max(780, price + random.gauss(-2.5, 55))
    rule, why = evaluate(RID, price, h, rules, ts)
    if rule and cooldown_ok(st, RID, rule, price, rules, ts):
        fires.append((day, round(price), rule))
        record_alert(st, RID, price, ts)
    h.append({"route_id": RID, "price": price, "ts": ts})
print(f"          90 days, 1 route -> {len(fires)} alerts "
      f"({len(fires)/90*6:.1f}/day across 6 routes)")
for d, p, r in fires:
    print(f"            day {d:>2}  ${p:>5}  {r}")
