"""Feasibility test: can this machine read Binance market data?

Run:  docker compose run --rm lake-sink python infra/check_binance.py
Expect 5 lines like "BTCUSDT 97012.10 0.003". HTTP 451 or a timeout = blocked location.
"""
import asyncio
import json

import requests
import websockets

URL = "wss://data-stream.binance.vision/ws/btcusdt@aggTrade"


async def main():
    print("REST ping:", requests.get("https://data-api.binance.vision/api/v3/ping", timeout=10).status_code)
    async with websockets.connect(URL) as ws:
        for _ in range(5):
            m = json.loads(await ws.recv())
            print(m["s"], m["p"], m["q"])
    print("OK: market data reachable")


asyncio.run(main())
