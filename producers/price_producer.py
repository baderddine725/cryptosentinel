"""Binance WebSocket -> Kafka.

One connection carries 2 streams per symbol:
  <symbol>@aggTrade  -> topic prices.trades  (every trade)
  <symbol>@kline_1m  -> topic prices.klines  (only CLOSED 1-minute candles)
Messages are normalised to our own schema, so a different exchange
(e.g. Coinbase as a fallback) only needs a new normalize() function.
"""
import asyncio
import json
import logging

from common.config import BINANCE_WS, KAFKA, SYMBOLS, TOPIC_KLINES, TOPIC_TRADES

log = logging.getLogger("price-producer")


def stream_url(symbols=SYMBOLS, base=BINANCE_WS):
    streams = "/".join(f"{s.lower()}@aggTrade/{s.lower()}@kline_1m" for s in symbols)
    return f"{base}/stream?streams={streams}"


def normalize(msg: dict):
    """Binance combined-stream message -> (topic, key, value) or None."""
    d = msg.get("data", msg)
    if d.get("e") == "aggTrade":
        return TOPIC_TRADES, d["s"], {
            "source": "binance", "symbol": d["s"], "event_time_ms": d["T"],
            "price": float(d["p"]), "qty": float(d["q"]),
            "is_buyer_maker": d["m"], "trade_id": d["a"]}
    if d.get("e") == "kline" and d["k"]["x"]:  # x = candle closed
        k = d["k"]
        return TOPIC_KLINES, d["s"], {
            "source": "binance", "symbol": d["s"], "open_time_ms": k["t"],
            "open": float(k["o"]), "high": float(k["h"]), "low": float(k["l"]),
            "close": float(k["c"]), "volume": float(k["v"]), "trades": k["n"],
            "taker_buy_volume": float(k["V"])}
    return None


async def run():
    import websockets
    from confluent_kafka import Producer

    producer = Producer({"bootstrap.servers": KAFKA, "acks": "all",
                         "linger.ms": 50, "compression.type": "lz4"})
    url, backoff, sent = stream_url(), 1, 0
    while True:
        try:
            async with websockets.connect(url, max_size=2**20) as ws:
                log.info("connected: %d symbols, %d streams", len(SYMBOLS), 2 * len(SYMBOLS))
                backoff = 1
                async for raw in ws:
                    out = normalize(json.loads(raw))
                    if out:
                        topic, key, value = out
                        producer.produce(topic, key=key, value=json.dumps(value))
                        producer.poll(0)
                        sent += 1
                        if topic == TOPIC_KLINES and value["symbol"] == SYMBOLS[0]:
                            log.info("minute closed (%s close=%s), %d messages sent so far",
                                     value["symbol"], value["close"], sent)
        except Exception as e:  # 24 h disconnect, network error, ...
            log.warning("reconnecting in %ss: %s", backoff, e)
            producer.flush(5)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    asyncio.run(run())
