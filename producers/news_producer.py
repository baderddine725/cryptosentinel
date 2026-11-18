"""Crypto news -> Kafka topic news.raw, every 2 minutes.

Sources: 3 RSS feeds (always) + CryptoPanic (if CRYPTOPANIC_URL and CRYPTOPANIC_KEY are set).
Each item is de-duplicated by URL and tagged with the coins it mentions.
We keep headline, link and a short summary only (never full articles).
"""
import calendar
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime

from common.config import KAFKA, TOPIC_NEWS

log = logging.getLogger("news-producer")

FEEDS = {
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph": "https://cointelegraph.com/rss",
    "decrypt": "https://decrypt.co/feed",
}
COINS = {
    "BTCUSDT": ["bitcoin", "btc"], "ETHUSDT": ["ethereum", "eth", "ether"],
    "SOLUSDT": ["solana", "sol"], "BNBUSDT": ["bnb"], "XRPUSDT": ["xrp", "ripple"],
    "DOGEUSDT": ["dogecoin", "doge"], "ADAUSDT": ["cardano", "ada"],
    "AVAXUSDT": ["avalanche", "avax"], "LINKUSDT": ["chainlink"], "PEPEUSDT": ["pepe"],
}
_PATTERNS = {s: [re.compile(rf"\b{re.escape(w)}\b") for w in words] for s, words in COINS.items()}


def tag(text: str) -> list[str]:
    t = text.lower()
    return [s for s, pats in _PATTERNS.items() if any(p.search(t) for p in pats)]


def strip_html(s: str, limit=500) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()[:limit]


def item_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()


def from_rss_entry(source: str, e) -> dict:
    published = e.get("published_parsed") or e.get("updated_parsed")
    ts = calendar.timegm(published) * 1000 if published else int(time.time() * 1000)
    summary = strip_html(e.get("summary", ""))
    return {"source": source, "published_ms": ts, "title": e.get("title", "").strip(),
            "url": e.get("link", ""), "summary": summary,
            "coins": tag(f"{e.get('title', '')} {summary}"), "sentiment": None}


def from_cryptopanic(p: dict):
    # CHECK these field names against one real response from your plan (they changed between versions)
    link = p.get("url") or p.get("original_url")
    if not link or not p.get("published_at"):
        return None
    published = datetime.fromisoformat(p["published_at"].replace("Z", "+00:00"))
    codes = [f"{c['code']}USDT" for c in p.get("currencies") or [] if c.get("code")]
    votes = p.get("votes") or {}
    return {"source": "cryptopanic", "published_ms": int(published.timestamp() * 1000),
            "title": p.get("title", ""), "url": link, "summary": "",
            "coins": [c for c in codes if c in COINS] or tag(p.get("title", "")),
            "sentiment": (votes.get("positive", 0) - votes.get("negative", 0)) if votes else None}


class NewsProducer:
    def __init__(self):
        from confluent_kafka import Producer
        self.producer = Producer({"bootstrap.servers": KAFKA})
        self.seen: set[str] = set()

    def emit(self, item: dict) -> bool:
        if not item or not item["url"]:
            return False
        item["id"] = item_id(item["url"])
        if item["id"] in self.seen:
            return False
        self.seen.add(item["id"])
        self.producer.produce(TOPIC_NEWS, key=item["id"], value=json.dumps(item))
        return True

    def poll_rss(self) -> int:
        import feedparser
        new = 0
        for src, url in FEEDS.items():
            for e in feedparser.parse(url).entries[:30]:
                new += self.emit(from_rss_entry(src, e))
        return new

    def poll_cryptopanic(self) -> int:
        import requests
        url, key = os.environ.get("CRYPTOPANIC_URL"), os.environ.get("CRYPTOPANIC_KEY")
        if not (url and key):
            return 0
        r = requests.get(url, params={"auth_token": key, "public": "true"}, timeout=15)
        r.raise_for_status()
        return sum(self.emit(from_cryptopanic(p)) for p in r.json().get("results", []))

    def run(self, every_s=120):
        while True:
            for poll in (self.poll_rss, self.poll_cryptopanic):
                try:
                    n = poll()
                    log.info("%s: %d new items", poll.__name__, n)
                except Exception as e:
                    log.warning("%s failed: %s", poll.__name__, e)
            self.producer.flush()
            time.sleep(every_s)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    NewsProducer().run()
