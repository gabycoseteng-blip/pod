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

# friendly labels for the Markets-tab JSON (data/markets.json)
LABELS = {
    "^GSPC": "S&P 500", "^IXIC": "Nasdaq", "^DJI": "Dow", "^RUT": "Russell 2000",
    "CLUSD": "WTI Crude", "BZUSD": "Brent", "GCUSD": "Gold",
    "USDPHP": "USD/PHP", "USDJPY": "USD/JPY", "EURUSD": "EUR/USD",
}


def _dir(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "flat"
    return "up" if x > 0 else "down" if x < 0 else "flat"


def _pct(x):
    try:
        return f"{'+' if float(x) >= 0 else ''}{round(float(x), 2)}%"
    except (TypeError, ValueError):
        return ""

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


def build_json(date):
    """Fetch the tape and return the Markets-tab schema (data/markets.json).
    Defensive: a dead route just yields an empty group rather than sinking it."""
    groups = []

    def idx_rows():
        rows = []
        by = {q.get("symbol"): q for q in get("batch-index-quotes?short=false")}
        for s in INDICES:
            q = by.get(s, {})
            if q:
                rows.append({"label": LABELS.get(s, s), "value": f"{q.get('price')}",
                             "change": _pct(q.get("changePercentage")), "dir": _dir(q.get("changePercentage"))})
        return rows

    def rate_rows():
        r = get("treasury-rates")[0]
        return [{"label": lbl, "value": f"{r.get(k)}%", "change": "", "dir": ""}
                for lbl, k in [("UST 2Y", "year2"), ("UST 10Y", "year10"), ("UST 30Y", "year30")]
                if r.get(k) is not None]

    def com_rows():
        rows = []
        by = {q.get("symbol"): q for q in get("batch-commodity-quotes")}
        for s in COMMODITIES:
            q = by.get(s, {})
            if q:
                rows.append({"label": LABELS.get(s, s), "value": f"{q.get('price')}",
                             "change": _pct(q.get("changePercentage")), "dir": _dir(q.get("changePercentage"))})
        return rows

    def fx_rows():
        rows = []
        by = {q.get("symbol"): q for q in get("batch-forex-quotes")}
        for s in FX:
            q = by.get(s, {})
            if q:
                rows.append({"label": LABELS.get(s, s), "value": f"{q.get('price')}",
                             "change": _pct(q.get("changePercentage")), "dir": _dir(q.get("changePercentage"))})
        return rows

    for name, fn in [("US Indices", idx_rows), ("Rates", rate_rows),
                     ("Commodities", com_rows), ("FX", fx_rows)]:
        try:
            rows = fn()
        except Exception as e:
            print(f"  ({name} unavailable: {type(e).__name__})", file=sys.stderr)
            rows = []
        if rows:
            groups.append({"name": name, "rows": rows})

    return {"date": date, "asOf": f"{date} close" if date else "",
            "groups": groups,
            "note": "Prior-session close — full levels so the show can stay brief."}


def main():
    # `--json PATH` writes the Markets-tab snapshot (data/markets.json schema) and exits;
    # otherwise print the compact text block for the research brief.
    args = sys.argv[1:]
    json_out = None
    if "--json" in args:
        i = args.index("--json")
        json_out = args[i + 1] if i + 1 < len(args) else None
        del args[i:i + 2]
    date = args[0] if args else ""

    if json_out:
        if not KEY:
            print(FALLBACK, file=sys.stderr)
            sys.exit(1)
        snap = build_json(date)
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2)
        n = sum(len(g["rows"]) for g in snap["groups"])
        print(f"OK  wrote {json_out}: {len(snap['groups'])} groups, {n} rows")
        return

    if not KEY:
        print(FALLBACK)
        return
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
