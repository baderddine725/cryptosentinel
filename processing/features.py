"""THE feature code. Pure functions on pandas, no Kafka, no AWS.

Used twice, so training and live inference see exactly the same inputs:
  - offline on 12 months of history  -> training data   (Phase 3a / 4)
  - live every minute from Kafka     -> model inputs    (Phase 3b)
"""
import numpy as np
import pandas as pd

DAY = 1440  # minutes
BAR_COLS = ["open", "high", "low", "close", "volume", "trades", "taker_buy_volume"]
HISTORY_CSV_COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
                    "quote_volume", "trades", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]

# Inputs of each model (news features come in version 2, once live news has been collected)
RCF_FEATURES = ["ret_z", "range_z", "volume_z", "trades_z", "imbalance", "idio_z", "r_1m"]
XGB_FEATURES = ["rv_5m", "rv_60m", "rv_1d", "r_5m", "r_15m", "r_60m", "volume_z", "trades_z",
                "imbalance", "mkt_r_1m", "mkt_rv_60m", "hour_sin", "hour_cos", "weekend"]


def read_history_csv(source) -> pd.DataFrame:
    """One Binance monthly CSV -> bars indexed by UTC minute (handles ms or µs timestamps)."""
    df = pd.read_csv(source, header=None, names=HISTORY_CSV_COLS)
    df["open_time"] = pd.to_numeric(df["open_time"], errors="coerce")
    df = df.dropna(subset=["open_time"])  # drops a header row if a file has one
    ms = np.where(df["open_time"] > 1e14, df["open_time"] // 1000, df["open_time"]).astype("int64")
    df.index = pd.to_datetime(ms, unit="ms", utc=True)
    df.index.name = "minute"
    return df[BAR_COLS].astype(float).sort_index()


def fill_gaps(bars: pd.DataFrame) -> pd.DataFrame:
    """One row per minute; a missing minute = no trades at the last price."""
    b = bars[~bars.index.duplicated(keep="last")][BAR_COLS].sort_index().asfreq("min")
    b["close"] = b["close"].ffill()
    for c in ("open", "high", "low"):
        b[c] = b[c].fillna(b["close"])
    return b.fillna({"volume": 0.0, "trades": 0.0, "taker_buy_volume": 0.0})


def _z(x: pd.Series, window=DAY) -> pd.Series:
    """How unusual is this minute vs the PREVIOUS `window` minutes (the minute itself excluded,
    so a spike cannot inflate its own baseline)."""
    past = x.shift(1).rolling(window, min_periods=60)
    std = past.std()
    return (x - past.mean()) / std.mask(std < 1e-12)       # flat history -> undefined, not infinite


def log_returns(bars: pd.DataFrame) -> pd.Series:
    return np.log(bars["close"]).diff()


def market_returns(all_bars: dict[str, pd.DataFrame]) -> pd.Series:
    """Equal-weighted 1-minute return of all coins: the 'whole market' move."""
    return pd.DataFrame({s: log_returns(b) for s, b in all_bars.items()}).mean(axis=1)


def compute_features(bars: pd.DataFrame, mkt_r: pd.Series) -> pd.DataFrame:
    """bars: one coin, UTC minute index, BAR_COLS (run fill_gaps first). mkt_r: market return."""
    f = pd.DataFrame(index=bars.index)
    r = log_returns(bars)
    f["r_1m"] = r
    for w in (5, 15, 60):
        f[f"r_{w}m"] = r.rolling(w).sum()
    for name, w in (("rv_5m", 5), ("rv_60m", 60), ("rv_1d", DAY)):
        f[name] = np.sqrt((r ** 2).rolling(w, min_periods=max(2, w // 2)).sum())
    sigma_1m = f["rv_60m"].shift(1) / np.sqrt(60)          # typical 1-min move over the PREVIOUS hour
    f["ret_z"] = r / sigma_1m                              # this minute's move in "sigmas"
    f["range_z"] = _z((bars["high"] - bars["low"]) / bars["close"])
    f["volume_z"] = _z(np.log1p(bars["volume"]))
    f["trades_z"] = _z(np.log1p(bars["trades"]))
    vol = bars["volume"].replace(0, np.nan)
    f["imbalance"] = (2 * bars["taker_buy_volume"] - bars["volume"]) / vol  # +1 all buys, -1 all sells
    m = mkt_r.reindex(bars.index)
    m_var = m.rolling(DAY, min_periods=120).var()
    beta = (r.rolling(DAY, min_periods=120).cov(m) / m_var.mask(m_var < 1e-18)).fillna(0.0)
    resid = r - beta * m                                   # the coin-specific part of the move
    f["idio_z"] = resid / resid.shift(1).rolling(60, min_periods=30).std()
    f["mkt_r_1m"] = m
    f["mkt_rv_60m"] = np.sqrt((m ** 2).rolling(60, min_periods=30).sum())
    hour = bars.index.hour + bars.index.minute / 60
    f["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    f["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    f["weekend"] = (bars.index.dayofweek >= 5).astype(int)
    return f.replace([np.inf, -np.inf], np.nan)


def future_log_rv(r: pd.Series, horizon=60) -> pd.Series:
    """XGBoost label: ln(realized volatility over the NEXT `horizon` minutes)."""
    future_var = (r ** 2).rolling(horizon).sum().shift(-horizon)
    return 0.5 * np.log(future_var.where(future_var > 0))
