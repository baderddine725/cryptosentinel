# CryptoSentinel

Real-time crypto risk monitoring on AWS: live prices and news flow through Kafka,
SageMaker models flag abnormal moves and forecast volatility, and an LLM agent
explains each shock with cited news.

**Milestone 1 (this version):** project skeleton, laptop/AWS switch, ingestion
(Binance + news into Kafka), the data lake (raw zone + 12-month history) and the
shared feature code, with 16 unit tests.

```
Binance WebSocket ─► price_producer ─► prices.trades / prices.klines ─┐
RSS + CryptoPanic ─► news_producer  ─► news.raw ──────────────────────┼─► Kafka ─► lake_sink ─► data lake (raw/)
Binance history files ─► download_history ────────────────────────────────────────────────► data lake (raw/history/)
                                                     processing/features.py  (shared by training and live)
```

## Laptop vs AWS: only `.env` changes

| | Laptop (`.env.local.example`) | EC2 (`.env.aws.example`) |
| --- | --- | --- |
| Kafka, producers, sink | Docker Compose | the same Docker Compose |
| Data lake | folder `./data/lake` (`STORAGE=local`) | S3 bucket (`STORAGE=s3`) |
| DynamoDB | DynamoDB Local container | Amazon DynamoDB |
| Notifications | printed in logs (`NOTIFY=log`) | Amazon SNS e-mail |

Lake keys are identical in both modes (`raw/prices.klines/dt=…/hour=…/…json`), so code never changes.

## Run it on your laptop (Windows: inside WSL2 Ubuntu)

Prerequisites: Docker Engine + Compose plugin, `make`, Git. On Windows, run everything
inside WSL2 so `network_mode: host` behaves like on EC2.

```bash
make env            # 1. creates .env from .env.local.example (edit it to add a CryptoPanic key, optional)
make up             # 2. builds the image, starts Kafka, DynamoDB Local, producers, sink
make topics         # 3. creates the 6 Kafka topics
make init           # 4. creates the DynamoDB tables and the lake folder
make test-binance   # 5. feasibility check: prints 5 BTC trades
make test           # 6. unit tests: expect "16 passed"
```

Then watch it work:

```bash
make logs           # "minute closed …" every minute, "poll_rss: N new items", "wrote N rows -> …"
make peek           # 3 messages from each topic
ls -R data/lake/raw | head    # one new file per topic every minute
```

## Download the training history (12 months, 10 coins)

```bash
make history        # ~120 CSV files, a few hundred MB, 10-20 min; safe to stop and resume
docker compose run --rm --no-deps lake-sink python tools/feature_preview.py BTCUSDT 2026-10
```

The preview prints the 5 most unusual minutes of that month with their features:
a first look at what the anomaly model will learn from.

## Milestone 1 checklist

- [ ] `make test-binance` prints trades
- [ ] `make test` → 16 passed
- [ ] `make peek` shows trades, closed candles (10 per minute) and news with `coins` tagged
- [ ] `data/lake/raw/prices.klines/…` gets a new file every minute
- [ ] `make history` finished; `feature_preview.py` prints a table

## Layout

```
common/        config.py (settings), storage.py (lake: folder or S3)
producers/     price_producer.py, news_producer.py
processing/    lake_sink.py, features.py
history/       download_history.py
infra/         create_topics.sh, init_resources.py, check_binance.py, user-data.sh, teardown.sh
tools/         feature_preview.py
tests/         unit tests (pytest)
```

## Deploying to AWS later

On the EC2 instance (see the build guide, Phase 0): clone the repo, `cp .env.aws.example .env`,
set `BUCKET`, then `docker compose up -d --build`, `bash infra/create_topics.sh`,
`docker compose run --rm lake-sink python infra/init_resources.py`.
Run `infra/teardown.sh` from your laptop at the end of every AWS session.

## Notes

- Use `make down` (stop), not `docker compose down`: `down` deletes the Kafka container and its topics.
- CryptoPanic's response fields have changed between API versions: run
  `curl "$CRYPTOPANIC_URL?auth_token=$CRYPTOPANIC_KEY&public=true" | head -c 1500` once and adjust
  `from_cryptopanic()` if needed (marked `CHECK`). Without a key, RSS feeds still work.
