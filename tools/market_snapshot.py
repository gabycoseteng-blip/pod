#!/usr/bin/env python3
"""
market_snapshot.py — one compact, deterministic market block for the brief,
instead of pasting several large MCP/JSON dumps into the model's context.

The token cost of the research step is dominated by broad tool results — e.g.
FMP `all-index-quotes` returns ~350 symbols when the show needs ~10, and
`biggest-gainers` returns 50 microcaps to surface one large-cap. This helper
fetches ONLY what the episode uses and prints ~20 tidy lines: the major US
indices (+ % change), the Treasury curve, WTI/Brent, gold, key FX
(USDPHP/USDJPY/EURUSD), and a short large-cap mover list.

The FMP MCP connector's key is NOT exposed to scripts, so this needs its own key:
    FMP_API_KEY=...  tools/market_snapshot.py [YYYY-MM-DD]

If FMP_API_KEY is unset it prints the fallback plan and exits 0 (non-fatal): use
targeted MCP calls rather than the broad ones —
    index-quote  ^GSPC ^IXIC ^DJI ^RUT      (not all-index-quotes)
    batch-quote  <the ~10 names you'll name> (not biggest-gainers/losers)
    economics    treasury-rates
    commodity    CLUSD BZUSD GCUSD
    forex        USDPHP USDJPY EURUSD

Routes below target FMP's `stable` API; adjust to your plan's paths if needed.
Each section is defensive so one failing route doesn't sink the whole snapshot.
"""
import json, os, sys, urllib.request, urllib.error

KEY = os.environ.get("FMP_API_KEY")
BASE = "https://financialmodelingprep.com/stable"
INDICES = ["^GSPC", "^IXIC", "^DJI", "^RUT"]
MOVERS = ["NVDA", "MSFT", "AAPL", "GOOGL", "AMZN", "META", "AVGO", "MU", "TSLA"]
COMMODITIES = ["CLUSD", "BZUSD", "GCUSD"]
FX = ["USDPHP", "USDJPY", "EURUSD"]

FALLBACK = """FMP_API_KEY not set — this wrapper needs its own key (the MCP
connector's key isn't visible to scripts). Fall back to TARGETED MCP calls so the
raw blobs never enter context:
  index-quote  ^GSPC ^IXIC ^DJI ^RUT         (NOT all-index-quotes: ~350 symbols)
  batch-quote  <the ~10 names you'll cite>   (NOT biggest-gainers/losers: 50 rows)
  economics    treasury-rates
  commodity    CLUSD (WTI) BZUSD (Brent) GCUSD (gold)
  forex        USDPHP USDJPY EURUSD
Better still: run the whole research fan-out in a subagent that returns only the
distilled numbers, so the JSON dumps stay out of the main thread entirely."""


def get(path):
    url = f"{BASE}/{path}{'&' if '?' in path else '?'}apikey={KEY}"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def section(title, fn):
    try:
        fn()
    except Exception as e:  # one dead route shouldn't kill the snapshot
        print(f"  ({title} unavailable: {type(e).__name__})")


def main():
    if not KEY:
        print(FALLBACK)
        return
    date = sys.argv[1] if len(sys.argv) > 1 else ""
    print(f"# Market snapshot {date}".rstrip())

    def indices():
        for q in get("batch-index-quotes?short=false"):
            if q.get("symbol") in INDICES:
                print(f"  {q['symbol']:<7} {q.get('price')}  ({q.get('changePercentage')}%)")

    def movers():
        syms = ",".join(MOVERS)
        for q in get(f"batch-quote?symbols={syms}"):
            print(f"  {q.get('symbol'):<6} {q.get('price')}  ({q.get('changePercentage')}%)")

    def rates():
        r = get("treasury-rates")[0]
        print(f"  UST 2y {r.get('year2')}  10y {r.get('year10')}  30y {r.get('year30')}")

    def commodities():
        for q in get("batch-commodity-quotes"):
            if q.get("symbol") in COMMODITIES:
                print(f"  {q['symbol']:<6} {q.get('price')}")

    def fx():
        for q in get("batch-forex-quotes"):
            if q.get("symbol") in FX:
                print(f"  {q['symbol']:<7} {q.get('price')}")

    print("Indices:");     section("indices", indices)
    print("Movers:");      section("movers", movers)
    print("Rates:");       section("rates", rates)
    print("Commodities:"); section("commodities", commodities)
    print("FX:");          section("fx", fx)


if __name__ == "__main__":
    main()
