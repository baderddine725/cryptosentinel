from producers.price_producer import normalize, stream_url

AGG_TRADE = {"stream": "btcusdt@aggTrade", "data": {
    "e": "aggTrade", "E": 1672515782136, "s": "BTCUSDT", "a": 12345, "p": "0.001", "q": "100",
    "f": 100, "l": 105, "T": 1672515782136, "m": True, "M": True}}


def kline(closed: bool):
    return {"stream": "btcusdt@kline_1m", "data": {
        "e": "kline", "E": 1672515782136, "s": "BTCUSDT", "k": {
            "t": 1672515720000, "T": 1672515779999, "s": "BTCUSDT", "i": "1m", "f": 100, "L": 200,
            "o": "0.0010", "c": "0.0020", "h": "0.0025", "l": "0.0015", "v": "1000", "n": 100,
            "x": closed, "q": "1.0000", "V": "500", "Q": "0.500", "B": "123456"}}}


def test_trade_is_normalized():
    topic, key, v = normalize(AGG_TRADE)
    assert (topic, key) == ("prices.trades", "BTCUSDT")
    assert v["price"] == 0.001 and v["qty"] == 100.0 and v["is_buyer_maker"] is True
    assert v["event_time_ms"] == 1672515782136


def test_only_closed_candles_are_sent():
    assert normalize(kline(closed=False)) is None
    topic, key, v = normalize(kline(closed=True))
    assert topic == "prices.klines" and key == "BTCUSDT"
    assert v["open_time_ms"] == 1672515720000
    assert (v["open"], v["high"], v["low"], v["close"]) == (0.001, 0.0025, 0.0015, 0.002)
    assert v["volume"] == 1000.0 and v["trades"] == 100 and v["taker_buy_volume"] == 500.0


def test_unknown_messages_are_ignored():
    assert normalize({"result": None, "id": 1}) is None


def test_stream_url_uses_market_data_host():
    url = stream_url(["BTCUSDT", "ETHUSDT"], base="wss://data-stream.binance.vision")
    assert url == ("wss://data-stream.binance.vision/stream?streams="
                   "btcusdt@aggTrade/btcusdt@kline_1m/ethusdt@aggTrade/ethusdt@kline_1m")
