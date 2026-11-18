import io

import numpy as np
import pandas as pd

from processing.features import (RCF_FEATURES, XGB_FEATURES, compute_features, fill_gaps,
                                  future_log_rv, log_returns, market_returns, read_history_csv)


def make_bars(n=3000, seed=0, start="2026-01-01"):
    idx = pd.date_range(start, periods=n, freq="min", tz="UTC")
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 1e-3, n)))
    vol = rng.uniform(5, 15, n)
    spread = rng.uniform(2e-4, 1e-3, n)
    return pd.DataFrame({"open": close, "high": close * (1 + spread), "low": close * (1 - spread),
                         "close": close, "volume": vol, "trades": rng.integers(20, 80, n).astype(float),
                         "taker_buy_volume": vol / 2}, index=idx)


def test_spike_is_visible_in_rcf_features():
    bars = make_bars()
    bars.iloc[-1, bars.columns.get_loc("close")] *= 1.03      # +3 % in the last minute
    bars.iloc[-1, bars.columns.get_loc("volume")] *= 8        # with 8x volume
    f = compute_features(fill_gaps(bars), pd.Series(0.0, index=bars.index))
    last = f.iloc[-1]
    assert last["ret_z"] > 10            # a huge move measured in sigmas
    assert last["volume_z"] > 3
    assert f[RCF_FEATURES].iloc[-1].notna().all()
    assert f[XGB_FEATURES].iloc[-1].notna().all()


def test_market_move_is_not_idiosyncratic():
    a, b = make_bars(seed=1), make_bars(seed=2)
    for bars in (a, b):                                         # both coins jump together
        bars.iloc[-1, bars.columns.get_loc("close")] *= 1.03
    mkt = market_returns({"A": a, "B": b})
    fa = compute_features(fill_gaps(a), mkt)
    assert fa["ret_z"].iloc[-1] > 10     # big move...
    assert abs(fa["idio_z"].iloc[-1]) < 3  # ...but explained by the market


def test_fill_gaps_inserts_missing_minutes():
    bars = make_bars(n=10).drop(index=make_bars(n=10).index[[3, 4]])
    filled = fill_gaps(bars)
    assert len(filled) == 10
    assert filled["volume"].iloc[3] == 0 and filled["close"].iloc[3] == filled["close"].iloc[2]


def test_label_looks_into_the_future_only():
    bars = make_bars(n=500)
    y = future_log_rv(log_returns(bars), horizon=60)
    assert y.iloc[-60:].isna().all()     # no future -> no label
    r = log_returns(bars)
    expected = 0.5 * np.log((r.iloc[101:161] ** 2).sum())
    assert np.isclose(y.iloc[100], expected)


def test_history_csv_ms_and_microseconds():
    row = "{t},100,101,99,100.5,12.5,0,1250,40,6.25,600,0\n"
    ms = row.format(t=1700000000000)
    us = row.format(t=1736000000000000)
    df = read_history_csv(io.StringIO(ms + us))
    assert list(df.index.year) == [2023, 2025]
    assert df.iloc[0]["close"] == 100.5 and df.iloc[0]["trades"] == 40
