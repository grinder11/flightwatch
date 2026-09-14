"""
Provider adapters. Each returns a list of dicts:

    {
        "price": float, "carrier": str,
        "stops": int|None, "duration_min": int|None,
        "outbound_stops": int|None, "outbound_duration_min": int|None,
        "outbound_depart": str|None, "outbound_arrive": str|None,
        "return_stops": int|None, "return_duration_min": int|None,
        "return_depart": str|None, "return_arrive": str|None,
        "return_routing": str, "full_read": bool,
    }

`*_depart`/`*_arrive` are local clock times as SerpApi reports them
("YYYY-MM-DD HH:MM", origin/destination local time respectively -- not
UTC, not the same timezone as each other), spanning the whole leg (first
segment's departure to last segment's arrival, connections included).

Every field above must be present on every dict any provider returns --
tracker.py subscripts them directly, no `.get()`.

This mirrors how Google Flights itself shows a multi-city itinerary: each
leg gets its own stop count and duration (outbound_* / return_*), never a
single merged number. `stops`/`duration_min` are OUR derived combined
values (worst-direction stop count, summed duration) for filtering and
alerting -- only known when `full_read` is True, since that's the only
case where the return leg's own routing has actually been read rather
than assumed. `stops` is the WORST direction's count, not the sum across
the trip: summing made `max_stops: 1` reject a perfectly good
one-stop-each-way itinerary, and it's also how Google's own stops filter
works (each leg must independently satisfy the cap).

Both APIs change response shapes occasionally. If a run returns zero offers,
print the raw payload before debugging anything else.

Confirmed empirically 2026-09: SerpApi's offer list can be incomplete
relative to Google's own live UI for the exact same search -- a nonstop
search returned only 2 of 3 nonstop outbound options the browser showed,
silently dropping the cheapest (JAL). This matters most for stops-allowed
routes, where a cheaper single leg could go unseen entirely. For full_read
nonstop routes specifically it's less consequential: the missing JAL
outbound didn't have a comparably-priced nonstop return partner anyway
(its cheapest nonstop-both-ways total was ~$3k, worse than the ~$1,579
pairing SerpApi did return) -- full_read is already answering "cheapest
matched round trip," not "cheapest single leg," so a leg missing from the
raw list doesn't necessarily mean a better matched total was missed.
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
        out_stops = per_dir[0] if per_dir else None
        ret_stops = per_dir[1] if len(per_dir) > 1 else None

        def leg_times(itin):
            segs = itin.get("segments", [])
            if not segs:
                return None, None
            return (segs[0].get("departure", {}).get("at"),
                    segs[-1].get("arrival", {}).get("at"))

        out_depart, out_arrive = leg_times(itins[0]) if itins else (None, None)
        ret_depart, ret_arrive = leg_times(itins[1]) if len(itins) > 1 else (None, None)
        return {
            "price": float(offer["price"]["grandTotal"]),
            "carrier": "/".join(sorted(c for c in carriers if c)) or "?",
            "stops": max(per_dir) if per_dir else 0,
            "duration_min": total or None,
            "outbound_stops": out_stops,
            "outbound_duration_min": None,
            "outbound_depart": out_depart,
            "outbound_arrive": out_arrive,
            "return_stops": ret_stops,
            "return_duration_min": None,
            "return_depart": ret_depart,
            "return_arrive": ret_arrive,
            "return_routing": "",
            "full_read": True,
        }


# ---------------------------------------------------------------------------
# SerpApi  --  scrapes Google Flights, so numbers match the UI
# Free tier 250 searches/month. Plain routes cost 1 request; a route with
# `full_read: true` costs 2 (a follow-up departure_token request to confirm
# the return leg). See README/CLAUDE.md for the current per-poll total.
#
# For a multi-city (type=3) search, the FIRST request only returns options
# for the OUTBOUND leg -- `flights`/`total_duration` describe that leg alone,
# even though `price` is already the full round-trip total (Google prices it
# assuming the cheapest matching return). The return leg's own routing is
# invisible until you follow that offer's `departure_token` in a second
# request. Confirmed empirically 2026-09: a leg-1 "$1,003" offer with a
# 12.5h Taipei layover matched a leg-2 return also via Taipei at the same
# $1,003 total -- the price was real, just paired with a return routing we
# couldn't see without the follow-up.
# ---------------------------------------------------------------------------

class SerpApi:
    BASE = "https://serpapi.com/search"

    # SerpApi reports an unusable key in the JSON `error` field, not an HTTP
    # status, and the wording has changed before -- match loosely. Both of
    # these mean "this key cannot serve requests," which is the only case
    # worth failing over for; a malformed query must still raise.
    ROTATE_ON = (
        "run out of searches", "exceeded", "quota", "plan limit",
        "invalid api key", "unauthorized",
    )

    def __init__(self):
        """Keys are tried in order, falling through to the next when one is
        exhausted or rejected. Single-key setups are unchanged: SERPAPI_KEY on
        its own still works exactly as before."""
        self.keys = []
        for k in os.environ.get("SERPAPI_KEYS", "").split(","):
            if k.strip():
                self.keys.append(k.strip())
        for var in ("SERPAPI_KEY", "SERPAPI_KEY_2", "SERPAPI_KEY_3"):
            k = os.environ.get(var, "").strip()
            if k and k not in self.keys:
                self.keys.append(k)
        if not self.keys:
            raise SystemExit(
                "no SerpApi key: set SERPAPI_KEY (and optionally SERPAPI_KEY_2), "
                "or SERPAPI_KEYS as a comma-separated list"
            )
        self.i = 0

    @classmethod
    def _should_rotate(cls, msg):
        m = (msg or "").lower()
        return any(s in m for s in cls.ROTATE_ON)

    def _base_params(self, route, cfg):
        # type=3 is multi-city. Verify param names against current SerpApi
        # docs before trusting a zero-result run.
        # api_key is attached per-request in _get(), so a mid-run key switch
        # applies to the follow-up request too.
        params = {
            "engine": "google_flights",
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
            # deep_search=true matches what the browser shows; the default
            # (false) is a cheaper, looser search that can return different
            # results. travel_class/gl/hl pinned rather than left to
            # SerpApi's per-request defaults.
            "deep_search": "true",
            "travel_class": "1",
            "gl": "us",
            "hl": "en",
        }
        if route.get("nonstop"):
            # SerpApi's own stops filter: 1 = nonstop only (2 = 1 stop or
            # fewer, 3 = 2 stops or fewer). This asks Google's search itself
            # for nonstop options -- unlike the client-side `max_stops`
            # filter in tracker.py, which only discards whatever offers
            # happened to already come back, it can't surface a nonstop
            # option that wasn't in that returned set to begin with.
            params["stops"] = "1"
        return params

    def _get(self, params, route_id):
        """One request, retried on the next key if this one is spent.

        The switch is sticky for the rest of the run -- once a key is known
        exhausted there is no point paying a failed request per route to
        rediscover it."""
        while True:
            n, total = self.i + 1, len(self.keys)
            r = requests.get(
                self.BASE, params=dict(params, api_key=self.keys[self.i]),
                timeout=TIMEOUT,
            )
            try:
                d = r.json()
            except ValueError:
                d = {}
            err = d.get("error")
            if not err and r.status_code >= 400:
                err = f"http {r.status_code}: {r.text[:200]}"

            if err and self._should_rotate(err) and self.i + 1 < total:
                print(f"[warn] serpapi key {n}/{total} unusable ({err}); "
                      f"switching to key {n + 1}")
                self.i += 1
                continue
            if err:
                # Only say "no keys left" when we actually ran out; a bad
                # query fails on the first key without rotating at all.
                spent = (" -- no keys left" if total > 1
                         and self._should_rotate(err) else "")
                raise RuntimeError(f"serpapi (key {n}/{total}){spent}: {err}")

            # Print what SerpApi actually searched -- multi_city_json silently
            # not being honored is indistinguishable from a real price otherwise.
            url = d.get("search_metadata", {}).get("google_flights_url")
            print(f"[serpapi] {route_id}: {url}")
            return d

    @staticmethod
    def _parse_leg(d):
        """One request's worth of offers for whichever leg it was for
        (outbound on the first request, return on a departure_token
        follow-up). Each dict describes only THAT leg, plus enough to chain
        to the next request."""
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
            route_ids = (
                [legs[0]["departure_airport"]["id"]] +
                [l["arrival_airport"]["id"] for l in legs]
            ) if legs else []
            out.append(
                {
                    "price": float(o["price"]),
                    "carrier": "/".join(sorted(names)) or "?",
                    "leg_stops": max(len(legs) - 1, 0) if legs else None,
                    "leg_duration_min": o.get("total_duration"),
                    # local clock times, first segment's departure to last
                    # segment's arrival -- spans any connection within the leg
                    "leg_depart": legs[0]["departure_airport"]["time"] if legs else None,
                    "leg_arrive": legs[-1]["arrival_airport"]["time"] if legs else None,
                    "departure_token": o.get("departure_token"),
                    "route_ids": route_ids,
                }
            )
        return out

    def search(self, route, cfg):
        params = self._base_params(route, cfg)
        if cfg.get("max_outbound_duration_min") is not None:
            params["max_duration"] = cfg["max_outbound_duration_min"]
        outbound = self._parse_leg(self._get(params, route["id"]))
        if not outbound:
            return []

        if not route.get("full_read"):
            return [
                {
                    "price": o["price"],
                    "carrier": o["carrier"],
                    "stops": None,
                    "duration_min": None,
                    "outbound_stops": o["leg_stops"],
                    "outbound_duration_min": o["leg_duration_min"],
                    "outbound_depart": o["leg_depart"],
                    "outbound_arrive": o["leg_arrive"],
                    "return_stops": None,
                    "return_duration_min": None,
                    "return_depart": None,
                    "return_arrive": None,
                    "return_routing": "",
                    "full_read": False,
                }
                for o in outbound
            ]

        # full_read: confirm the cheapest outbound offer's actual return
        # leg with a second (quota-costing) request. Google's own UI does
        # the same thing -- picking an outbound flight loads a second list
        # of return options priced against that specific choice.
        cheapest = min(outbound, key=lambda o: o["price"])

        def outbound_only(reason):
            print(f"[warn] {route['id']}: {reason}; reporting outbound-only "
                  f"for this run")
            return [
                {
                    "price": cheapest["price"],
                    "carrier": cheapest["carrier"],
                    "stops": None,
                    "duration_min": None,
                    "outbound_stops": cheapest["leg_stops"],
                    "outbound_duration_min": cheapest["leg_duration_min"],
                    "outbound_depart": cheapest["leg_depart"],
                    "outbound_arrive": cheapest["leg_arrive"],
                    "return_stops": None,
                    "return_duration_min": None,
                    "return_depart": None,
                    "return_arrive": None,
                    "return_routing": "",
                    "full_read": False,
                }
            ]

        token = cheapest.get("departure_token")
        if not token:
            return outbound_only("full_read requested but no departure_token "
                                  "on the cheapest offer")

        params2 = self._base_params(route, cfg)
        params2["departure_token"] = token
        returning = self._parse_leg(self._get(params2, f"{route['id']} (return)"))
        if not returning:
            return outbound_only("full_read follow-up returned no "
                                  "return-leg offers")

        # Google prices the leg-1 list assuming the cheapest matching return,
        # so picking the lowest-priced return option here is what reproduces
        # the total already shown for `cheapest` -- confirmed empirically:
        # a $1,003 leg-1 offer via a 12.5h Taipei layover matched a return
        # also via Taipei at that same $1,003 total.
        back = min(returning, key=lambda o: o["price"])
        # Each leg keeps its own stop count/duration, exactly as Google's UI
        # shows them (outbound and return are never merged in the display).
        # `stops`/`duration_min` below are OUR derived combined values --
        # worst direction (same convention as `max_stops` everywhere else)
        # and summed duration -- for filtering and alerting, not a native
        # Google field.
        combined_stops = max(cheapest["leg_stops"] or 0, back["leg_stops"] or 0)
        combined_duration = (
            (cheapest["leg_duration_min"] or 0) + (back["leg_duration_min"] or 0)
        ) or None
        # The cheapest matching return is often a completely different
        # airline than the outbound (confirmed empirically: a United outbound
        # paired with a Philippine Airlines return via Manila on what Google's
        # UI flags as a separate ticket). Collapsing to just the outbound
        # carrier hid that. SerpApi exposes no explicit "separate tickets"
        # flag, but showing both real carriers when they differ is simpler
        # and doesn't depend on guessing Google's internal definition.
        carrier = (
            cheapest["carrier"] if cheapest["carrier"] == back["carrier"]
            else f"{cheapest['carrier']} out / {back['carrier']} back"
        )
        return [
            {
                "price": back["price"],
                "carrier": carrier,
                "stops": combined_stops,
                "duration_min": combined_duration,
                "outbound_stops": cheapest["leg_stops"],
                "outbound_duration_min": cheapest["leg_duration_min"],
                "outbound_depart": cheapest["leg_depart"],
                "outbound_arrive": cheapest["leg_arrive"],
                "return_stops": back["leg_stops"],
                "return_duration_min": back["leg_duration_min"],
                "return_depart": back["leg_depart"],
                "return_arrive": back["leg_arrive"],
                "return_routing": "-".join(back["route_ids"]),
                "full_read": True,
            }
        ]


def get_provider(name):
    try:
        return {"amadeus": Amadeus, "serpapi": SerpApi}[name]()
    except KeyError:
        raise SystemExit(f"unknown provider {name!r}; use amadeus or serpapi")
