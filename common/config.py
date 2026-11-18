"""Settings read from the environment (.env). One place, so every service agrees."""
import os

KAFKA = os.environ.get("KAFKA", "localhost:9092")
SYMBOLS = [s.strip().upper() for s in os.environ.get(
    "SYMBOLS", "btcusdt,ethusdt,solusdt,bnbusdt,xrpusdt,dogeusdt,adausdt,avaxusdt,linkusdt,pepeusdt"
).split(",") if s.strip()]

# Binance market-data-only host: same streams as stream.binance.com, no key,
# and the one to use from AWS us-east-1 (keep it on the laptop too, for parity).
BINANCE_WS = os.environ.get("BINANCE_WS", "wss://data-stream.binance.vision")
BINANCE_REST = os.environ.get("BINANCE_REST", "https://data-api.binance.vision")

TOPIC_TRADES = "prices.trades"
TOPIC_KLINES = "prices.klines"
TOPIC_NEWS = "news.raw"
