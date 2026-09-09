"""
Provider adapters. Each returns a list of dicts:

    {"price": float, "carrier": str, "stops": int, "duration_min": int|None}

`stops` is the WORST direction's stop count, not the sum across the trip.
Summing made `max_stops: 1` reject a perfectly good one-stop-each-way
itinerary.

Both APIs change response shapes occasionally. If a run returns zero offers,
print the raw payload before debugging anything else.
"""

import os
import re
import time
import requests

TIMEOUT = 30


# ---------------------------------------------------------------------------
# Amadeus Self-Service  --  free tier, official GDS inventory
# Docs: developers.amadeus.com  (Flight Offers Search v2)
# ---------------------------------------------------------------------------

class Amadeus:
    # Swap to https://api.amadeus.com once you move off the test key.
    BASE = "https://test.api.amadeus.com"

    def __init__(self):
        self.key = os.environ["AMADEUS_KEY"]
        self.secret = os.environ["AMADEUS_SECRET"]
        self._token = None
        self._token_expires = 0

    def _auth(self):
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        r = requests.post(
            f"{self.BASE}/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.key,
                "client_secret": self.secret,
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        d = r.json()
        self._token = d["access_token"]
        self._token_expires = time.time() + d.get("expires_in", 1799)
        return self._token

    def search(self, route, cfg):
        """Open jaw = two originDestinations. The GET form only does simple
        round trips, so multi-city goes through POST."""
        body = {
            "currencyCode": cfg["currency"],
            "originDestinations": [
                {
                    "id": "1",
                    "originLocationCode": route["origin"],
                    "destinationLocationCode": route["destination"],
                    "departureDateTimeRange": {"date": str(route["depart"])},
                },
                {
                    "id": "2",
                    "originLocationCode": route["return_origin"],
                    "destinationLocationCode": route["return_destination"],
                    "departureDateTimeRange": {"date": str(route["return"])},
                },
            ],
            "travelers": [
                {"id": str(i + 1), "travelerType": "ADULT",
                 "fareOptions": ["STANDARD"]}
                for i in range(cfg["adults"])
            ],
            "sources": ["GDS"],
            "searchCriteria": {
                "maxFlightOffers": 20,
                "flightFilters": {
                    "cabinRestrictions": [
                        {
                            "cabin": cfg["cabin"],
                            "coverage": "MOST_SEGMENTS",
                            "originDestinationIds": ["1", "2"],
                        }
                    ]
                },
            },
        }
        r = requests.post(
            f"{self.BASE}/v2/shopping/flight-offers",
            json=body,
            headers={
                "Authorization": f"Bearer {self._auth()}",
                "Content-Type": "application/json",
                # FIX: the POST form of Flight Offers Search is rejected
                # without this. Its absence was why every run returned an
                # error rather than offers.
                "X-HTTP-Method-Override": "GET",
            },
            timeout=TIMEOUT,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"amadeus {r.status_code}: {r.text[:400]}")
        return [self._parse(o) for o in r.json().get("data", [])]

    @staticmethod
    def _iso_duration_min(s):
        """PT14H15M -> 855. Returns None on anything unexpected."""
        if not s:
            return None
        m = re.match(r"^P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?$", s)
        if not m:
            return None
        d, h, mi = (int(x) if x else 0 for x in m.groups())
        return d * 1440 + h * 60 + mi

    @classmethod
    def _parse(cls, offer):
        itins = offer.get("itineraries", [])
        # per-direction stops, then take the worst
        per_dir = [max(len(i.get("segments", [])) - 1, 0) for i in itins]
        carriers = {
            s.get("carrierCode")
            for i in itins
            for s in i.get("segments", [])
        }
        total = sum(
            cls._iso_duration_min(i.get("duration")) or 0 for i in itins
        )
        return {
            "price": float(offer["price"]["grandTotal"]),
            "carrier": "/".join(sorted(c for c in carriers if c)) or "?",
            "stops": max(per_dir) if per_dir else 0,
            "duration_min": total or None,
        }


# ---------------------------------------------------------------------------
# SerpApi  --  scrapes Google Flights, so numbers match the UI
# Free tier ~100 searches/month. Six routes daily = ~180/mo, so you need a
# paid tier or an every-other-day schedule.
# ---------------------------------------------------------------------------

class SerpApi:
    BASE = "https://serpapi.com/search"

    def __init__(self):
        self.key = os.environ["SERPAPI_KEY"]

    def search(self, route, cfg):
        # type=3 is multi-city. Verify param names against current SerpApi
        # docs before trusting a zero-result run.
        params = {
            "engine": "google_flights",
            "api_key": self.key,
            "currency": cfg["currency"],
            "adults": cfg["adults"],
            "type": "3",
            "multi_city_json": (
                f'[{{"departure_id":"{route["origin"]}",'
                f'"arrival_id":"{route["destination"]}",'
                f'"date":"{route["depart"]}"}},'
                f'{{"departure_id":"{route["return_origin"]}",'
                f'"arrival_id":"{route["return_destination"]}",'
                f'"date":"{route["return"]}"}}]'
            ),
        }
        r = requests.get(self.BASE, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        d = r.json()
        if d.get("error"):
            raise RuntimeError(f"serpapi: {d['error']}")
        offers = (d.get("best_flights") or []) + (d.get("other_flights") or [])
        out = []
        for o in offers:
            if o.get("price") is None:
                continue
            legs = o.get("flights", [])
            # FIX: this line was `sorted({...}) - {""}`, i.e. list minus set,
            # a TypeError on every single offer. The SerpApi path could never
            # have returned anything.
            names = {l.get("airline", "") for l in legs} - {""}
            out.append(
                {
                    "price": float(o["price"]),
                    "carrier": "/".join(sorted(names)) or "?",
                    # two origin-destinations, so segments beyond 2 are stops.
                    # Approximate: SerpApi does not split legs by direction.
                    "stops": max(len(legs) - 2, 0),
                    "duration_min": o.get("total_duration"),
                }
            )
        return out


def get_provider(name):
    try:
        return {"amadeus": Amadeus, "serpapi": SerpApi}[name]()
    except KeyError:
        raise SystemExit(f"unknown provider {name!r}; use amadeus or serpapi")
