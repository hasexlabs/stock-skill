#!/usr/bin/env python3
"""Fetch daily Yahoo chart data and summarize price history for research.

Example:
  python price_history.py CODA RELL ERII --years 2 --out-dir ./price_data

This script is a research aid, not a trading system. It does not calculate fair value.
"""
import argparse
import csv
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests


def fetch(symbol: str, start: int, end: int, out_dir: Path) -> dict:
    symbol = symbol.upper()
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={start}&period2={end}&interval=1d"
        "&events=history&includeAdjustedClose=true"
    )
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    response.raise_for_status()
    payload = response.json().get("chart", {}).get("result")
    if not payload:
        raise RuntimeError(f"No chart data returned for {symbol}")
    result = payload[0]
    quote = result["indicators"]["quote"][0]
    rows = []
    for i, timestamp in enumerate(result.get("timestamp", [])):
        close = quote["close"][i]
        if close is None:
            continue
        rows.append({
            "date": datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat(),
            "open": quote["open"][i],
            "high": quote["high"][i],
            "low": quote["low"][i],
            "close": close,
            "volume": quote["volume"][i],
        })
    if not rows:
        raise RuntimeError(f"No usable rows returned for {symbol}")
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{symbol.lower()}_daily.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    closes = [row["close"] for row in rows]
    running_high = 0.0
    max_drawdown = 0.0
    peak_date = trough_date = ""
    peak_price = trough_price = 0.0
    local_lows, local_highs = [], []
    for i, row in enumerate(rows):
        if row["close"] > running_high:
            running_high = row["close"]
            peak_date, peak_price = row["date"], row["close"]
        drawdown = row["close"] / running_high - 1
        if drawdown < max_drawdown:
            max_drawdown = drawdown
            trough_date, trough_price = row["date"], row["close"]
        if 2 <= i < len(rows) - 2:
            window = closes[i - 2 : i + 3]
            if closes[i] == min(window):
                local_lows.append((row["date"], row["close"]))
            if closes[i] == max(window):
                local_highs.append((row["date"], row["close"]))

    def average(days):
        return statistics.mean(closes[-days:]) if len(closes) >= days else None

    return {
        "symbol": symbol,
        "csv": str(csv_path),
        "start": rows[0]["date"],
        "end": rows[-1]["date"],
        "observations": len(rows),
        "latest": closes[-1],
        "low": min(closes),
        "low_date": rows[closes.index(min(closes))]["date"],
        "high": max(closes),
        "high_date": rows[closes.index(max(closes))]["date"],
        "median": statistics.median(closes),
        "q25": statistics.quantiles(closes, n=4)[0],
        "q75": statistics.quantiles(closes, n=4)[2],
        "avg20": average(20),
        "avg60": average(60),
        "avg120": average(120),
        "max_drawdown_pct": max_drawdown * 100,
        "peak": f"{peak_date} ${peak_price:.4f}",
        "trough": f"{trough_date} ${trough_price:.4f}",
        "recent_lows": " ".join(f"{d}:{p:.2f}" for d, p in local_lows[-10:]),
        "recent_highs": " ".join(f"{d}:{p:.2f}" for d, p in local_highs[-10:]),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="+", help="Ticker symbols")
    parser.add_argument("--years", type=float, default=2.0)
    parser.add_argument("--out-dir", type=Path, default=Path("price_data"))
    args = parser.parse_args()
    end = int(time.time())
    start = int(end - args.years * 365.25 * 24 * 60 * 60)
    with ThreadPoolExecutor(max_workers=min(8, len(args.symbols))) as pool:
        futures = [pool.submit(fetch, symbol, start, end, args.out_dir) for symbol in args.symbols]
        results = [future.result() for future in futures]
    fields = [
        "symbol", "start", "end", "observations", "latest", "low", "low_date", "high", "high_date",
        "median", "q25", "q75", "avg20", "avg60", "avg120", "max_drawdown_pct", "peak", "trough",
        "recent_lows", "recent_highs", "csv",
    ]
    writer = csv.DictWriter(__import__("sys").stdout, fieldnames=fields, delimiter="\t")
    writer.writeheader()
    writer.writerows(results)


if __name__ == "__main__":
    main()
