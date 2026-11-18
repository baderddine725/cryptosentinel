#!/bin/bash
# Create the Kafka topics (safe to run again).
set -e
for t in prices.trades prices.klines news.raw features.1m alerts.anomaly alerts.explained; do
  docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 \
    --create --if-not-exists --topic "$t" --partitions 3 --replication-factor 1
done
docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
