# Shortcuts. On the laptop use the "local" targets; on EC2 use plain docker compose.
LOCAL = docker compose -f docker-compose.yml -f docker-compose.local.yml
RUN   = $(LOCAL) run --rm --no-deps lake-sink

.PHONY: env up topics init test-binance history test logs peek down

env:            ## create .env for the laptop (once)
	cp -n .env.local.example .env

up:             ## build and start everything on the laptop
	$(LOCAL) up -d --build

topics:         ## create the Kafka topics
	bash infra/create_topics.sh

init:           ## create DynamoDB tables / lake folder (S3 + SNS on AWS)
	$(RUN) python infra/init_resources.py

test-binance:   ## feasibility test for Binance market data
	$(RUN) python infra/check_binance.py

history:        ## download 12 months of 1-minute candles into the lake
	$(RUN) python history/download_history.py

test:           ## unit tests
	$(RUN) pytest -q

logs:           ## follow the producers and the sink
	$(LOCAL) logs -f price-producer news-producer lake-sink

peek:           ## print 3 messages from each topic
	for t in prices.trades prices.klines news.raw; do \
	  echo "== $$t"; \
	  docker compose exec -T kafka /opt/kafka/bin/kafka-console-consumer.sh \
	    --bootstrap-server localhost:9092 --topic $$t --from-beginning --max-messages 3 --timeout-ms 20000; \
	done

down:           ## stop (keeps containers and topics)
	$(LOCAL) stop
