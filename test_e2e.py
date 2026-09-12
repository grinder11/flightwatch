"""End-to-end: stub provider -> tracker.main() -> CSV -> analyze.py. No network."""
import random, sys, types, subprocess, csv
from datetime import datetime, timezone, timedelta
from pathlib import Path

import providers

CARRIERS = ["NH", "JL", "UA", "SQ/NH", "BR"]


class Stub:
    """Deterministic fake fares, one seeded walk per route."""
    walks = {}

    def search(self, route, cfg):
        rid = route["id"]
        if rid not in Stub.walks:
            random.seed(hash(rid) % 9999)
            Stub.walks[rid] = 1250 + random.uniform(-120, 180)
        Stub.walks[rid] = max(700, Stub.walks[rid] + random.gauss(-1, 45))
        p = Stub.walks[rid]
        full_read = route.get("full_read", False)

        def offer(price, carrier):
            out_stops = random.choice([0, 0, 1, 1, 2])
            out_dur = random.choice([660, 780, 900])
            out_depart, out_arrive = "2027-05-14 08:45", "2027-05-15 15:05"
            if full_read:
                ret_stops = random.choice([0, 0, 1, 1, 2])
                ret_dur = random.choice([660, 780, 900])
                ret_depart, ret_arrive = "2027-05-23 16:55", "2027-05-24 11:10"
                return {
                    "price": round(price, 2), "carrier": carrier,
                    "stops": max(out_stops, ret_stops),
                    "duration_min": out_dur + ret_dur,
                    "outbound_stops": out_stops, "outbound_duration_min": out_dur,
                    "outbound_depart": out_depart, "outbound_arrive": out_arrive,
                    "return_stops": ret_stops, "return_duration_min": ret_dur,
                    "return_depart": ret_depart, "return_arrive": ret_arrive,
                    "return_routing": "SFO-HND-KIX-SFO", "full_read": True,
                }
            return {
                "price": round(price, 2), "carrier": carrier,
                "stops": None, "duration_min": None,
                "outbound_stops": out_stops, "outbound_duration_min": out_dur,
                "outbound_depart": out_depart, "outbound_arrive": out_arrive,
                "return_stops": None, "return_duration_min": None,
                "return_depart": None, "return_arrive": None,
                "return_routing": "", "full_read": False,
            }

        return [
            offer(p, random.choice(CARRIERS)),
            offer(p * 1.15, "UA"),
        ]


providers.get_provider = lambda name: Stub()
sys.modules["providers"].get_provider = providers.get_provider

import tracker
tracker.get_provider = lambda name: Stub()

# Backdate: run tracker 45 times, one per simulated day.
Path("data").mkdir(exist_ok=True)
for f in ("data/history.csv", "data/alert_state.json"):
    Path(f).unlink(missing_ok=True)

real_dt = tracker.datetime
DAY = [0]


class FakeDT(real_dt):
    @classmethod
    def now(cls, tz=None):
        return real_dt(2027, 1, 1, 14, 10, tzinfo=timezone.utc) + timedelta(days=DAY[0])


tracker.datetime = FakeDT
sent = []
tracker.notify = lambda text, cfg: sent.append(text)

sys.argv = ["tracker.py"]
for d in range(45):
    DAY[0] = d
    tracker.main()

print("\n" + "=" * 70)
rows = list(csv.DictReader(open("data/history.csv")))
n_routes = len({r["route_id"] for r in rows})
print(f"45 simulated days x {n_routes} routes")
print(f"  history.csv rows: {len(rows)}  (expect {45 * n_routes})")
print(f"  alerts sent:      {len(sent)} notifications")
print(f"  blank duration_min cells: {sum(1 for r in rows if r['duration_min']=='')}")
print("=" * 70)
if sent:
    print("\nLAST ALERT PAYLOAD:\n" + sent[-1])
