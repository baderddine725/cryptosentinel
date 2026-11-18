"""Create the storage resources the pipeline needs. Safe to run again.

Laptop (MODE=local): DynamoDB tables in DynamoDB Local + the data-lake folder.
EC2    (MODE=aws):   DynamoDB tables + S3 bucket + SNS topic in your AWS account.

Run:  docker compose run --rm lake-sink python infra/init_resources.py
"""
import os

import boto3
from botocore.exceptions import ClientError

from common.storage import LOCAL_ROOT

TABLES = {
    # live features + model scores, last 48 h
    "cs-live": [("symbol", "S", "HASH"), ("minute", "N", "RANGE")],
    # news by coin ("MARKET" when no coin is tagged)
    "cs-news": [("coin", "S", "HASH"), ("ts_id", "S", "RANGE")],
    # explained alerts written by the agent
    "cs-alerts": [("alert_id", "S", "HASH")],
}
TTL = {"cs-live": "expires", "cs-news": "expires"}


def create_tables():
    ddb = boto3.client("dynamodb")
    existing = set(ddb.list_tables()["TableNames"])
    for name, keys in TABLES.items():
        if name in existing:
            print(f"table {name}: exists")
            continue
        ddb.create_table(
            TableName=name,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": k, "AttributeType": t} for k, t, _ in keys],
            KeySchema=[{"AttributeName": k, "KeyType": r} for k, _, r in keys],
        )
        ddb.get_waiter("table_exists").wait(TableName=name)
        print(f"table {name}: created")
        if name in TTL:
            try:
                ddb.update_time_to_live(TableName=name, TimeToLiveSpecification={
                    "Enabled": True, "AttributeName": TTL[name]})
            except ClientError as e:  # DynamoDB Local may ignore TTL; harmless
                print(f"  ttl skipped: {e.response['Error']['Code']}")


def create_bucket():
    bucket = os.environ["BUCKET"]
    s3 = boto3.client("s3")
    try:
        s3.head_bucket(Bucket=bucket)
        print(f"bucket {bucket}: exists")
    except ClientError:
        s3.create_bucket(Bucket=bucket)  # us-east-1 needs no location constraint
        print(f"bucket {bucket}: created")


def create_topic():
    arn = boto3.client("sns").create_topic(Name="cs-alerts")["TopicArn"]  # idempotent
    print(f"SNS topic: {arn}\n  -> put it in .env as SNS_TOPIC_ARN and subscribe your e-mail:")
    print(f"  aws sns subscribe --topic-arn {arn} --protocol email --notification-endpoint you@example.com")


if __name__ == "__main__":
    create_tables()
    if os.environ.get("STORAGE", "local") == "s3":
        create_bucket()
    else:
        LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
        print(f"data lake folder: {LOCAL_ROOT}")
    if os.environ.get("NOTIFY") == "sns":
        create_topic()
