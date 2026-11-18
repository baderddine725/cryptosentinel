from datetime import date, datetime, timezone

from common import storage
from history.download_history import history_key, last_months
from processing.lake_sink import raw_key


def test_local_lake_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "BACKEND", "local")
    monkeypatch.setattr(storage, "LOCAL_ROOT", tmp_path)
    key = "raw/prices.klines/dt=2026-11-20/hour=14/1.json"
    assert not storage.exists(key)
    where = storage.put_bytes(key, b'{"a":1}')
    assert storage.exists(key) and (tmp_path / key).read_bytes() == b'{"a":1}'
    assert where.endswith("1.json")


def test_last_complete_months():
    assert last_months(3, date(2026, 2, 10)) == ["2026-01", "2025-12", "2025-11"]


def test_lake_keys_are_partitioned():
    now = datetime(2026, 11, 20, 14, 5, tzinfo=timezone.utc)
    assert raw_key("prices.klines", now).startswith("raw/prices.klines/dt=2026-11-20/hour=14/")
    assert history_key("BTCUSDT", "2026-10") == \
        "raw/history/klines/symbol=BTCUSDT/BTCUSDT-1m-2026-10.csv"
