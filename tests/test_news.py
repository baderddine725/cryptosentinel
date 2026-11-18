import time

from producers.news_producer import from_cryptopanic, from_rss_entry, item_id, strip_html, tag


def test_tagging_uses_whole_words():
    assert tag("Solana ETF approved; Bitcoin follows") == ["BTCUSDT", "SOLUSDT"]
    assert tag("A new solution for payments") == []          # 'sol' inside 'solution' is not SOL
    assert tag("Chainlink oracle update") == ["LINKUSDT"]
    assert tag("Click this link to read more") == []        # plain 'link' is not LINK


def test_rss_entry():
    e = {"title": "Ethereum upgrade goes live", "link": "https://example.com/a",
         "summary": "<p>The <b>ETH</b> network upgraded.</p>",
         "published_parsed": time.gmtime(1763650800)}
    item = from_rss_entry("coindesk", e)
    assert item["published_ms"] == 1763650800000
    assert item["summary"] == "The ETH network upgraded."
    assert item["coins"] == ["ETHUSDT"]


def test_cryptopanic_post():
    p = {"title": "XRP jumps after ruling", "published_at": "2026-11-20T14:00:00Z",
         "url": "https://cryptopanic.com/news/1", "currencies": [{"code": "XRP"}, {"code": "FOO"}],
         "votes": {"positive": 7, "negative": 2}}
    item = from_cryptopanic(p)
    assert item["coins"] == ["XRPUSDT"] and item["sentiment"] == 5
    assert item["published_ms"] == 1795183200000
    assert from_cryptopanic({"title": "no link"}) is None


def test_helpers():
    assert strip_html("<div>a  <br/> b</div>") == "a b"
    assert item_id("https://x") == item_id("https://x") != item_id("https://y")
