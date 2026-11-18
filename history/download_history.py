"""Download the last N complete months of 1-minute candles from Binance's public data site
into the data lake:  raw/history/klines/symbol=BTCUSDT/BTCUSDT-1m-2026-10.csv

Run:  make history            (or: python history/download_history.py --months 12)
Already-downloaded files are skipped, so you can stop and resume.
The CSVs have NO header: open_time, open, high, low, close, volume, close_time,
quote_volume, trades, taker_buy_volume, taker_buy_quote_volume, ignore
"""
import argparse
import io
import zipfile
from datetime import date

from common.config import SYMBOLS
from common.storage import exists, put_bytes

BASE = "https://data.binance.vision/data/spot/monthly/klines"


def last_months(n: int, today: date | None = None) -> list[str]:
    """The n most recent COMPLETE months, newest first, as 'YYYY-MM'."""
    today = today or date.today()
    y, m, out = today.year, today.month, []
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(f"{y}-{m:02d}")
    return out


def history_key(symbol: str, ym: str) -> str:
    return f"raw/history/klines/symbol={symbol}/{symbol}-1m-{ym}.csv"


def main(months: int):
    import requests

    ok = skipped = missing = 0
    for sym in SYMBOLS:
        for ym in last_months(months):
            key = history_key(sym, ym)
            if exists(key):
                skipped += 1
                continue
            url = f"{BASE}/{sym}/1m/{sym}-1m-{ym}.zip"
            r = requests.get(url, timeout=120)
            if r.status_code != 200:
                print("missing", url)  # e.g. a month before the coin was listed
                missing += 1
                continue
            csv_bytes = zipfile.ZipFile(io.BytesIO(r.content)).read(f"{sym}-1m-{ym}.csv")
            print("ok", sym, ym, f"{len(csv_bytes) / 1e6:.1f} MB ->", put_bytes(key, csv_bytes))
            ok += 1
    print(f"done: {ok} downloaded, {skipped} already there, {missing} missing")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--months", type=int, default=12)
    main(p.parse_args().months)
