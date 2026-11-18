"""See the features on real data: the 5 most unusual minutes of a month, for one coin.

Run (after `make history`):
  docker compose run --rm --no-deps lake-sink python tools/feature_preview.py BTCUSDT 2026-10
"""
import sys

import pandas as pd

from common.config import SYMBOLS
from common.storage import location
from processing.features import RCF_FEATURES, compute_features, fill_gaps, market_returns, read_history_csv

symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
month = sys.argv[2]
path = lambda s: f"{location('raw/history/klines')}/symbol={s}/{s}-1m-{month}.csv"

bars = {s: fill_gaps(read_history_csv(path(s))) for s in SYMBOLS}
f = compute_features(bars[symbol], market_returns(bars))
pd.set_option("display.width", 160, "display.precision", 2)
print(f"{symbol} {month}: {len(f):,} minutes\n")
print("5 most unusual minutes by |ret_z| (move in sigmas):")
top = f.reindex(f["ret_z"].abs().sort_values(ascending=False).index[:5])
print(top[RCF_FEATURES].assign(close=bars[symbol]["close"]))
