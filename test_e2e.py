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
        return [
            {"price": round(p, 2), "carrier": random.choice(CARRIERS),
             "stops": random.choice([0, 0, 1, 1, 2]), "duration_min": random.choice([660, 780, None])},
            {"price": round(p * 1.15, 2), "carrier": "UA", "stops": 0, "duration_min": 640},
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
print(f"45 simulated days x 6 routes")
rows = list(csv.DictReader(open("data/history.csv")))
print(f"  history.csv rows: {len(rows)}  (expect 270)")
print(f"  alerts sent:      {len(sent)} notifications")
print(f"  blank duration_min cells: {sum(1 for r in rows if r['duration_min']=='')}")
print("=" * 70)
if sent:
    print("\nLAST ALERT PAYLOAD:\n" + sent[-1])
