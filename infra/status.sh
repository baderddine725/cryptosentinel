#!/bin/bash
# Read-only overview of every CryptoSentinel AWS resource. Changes nothing.
# Run after bootstrap_aws.sh (is everything there?) and before leaving (is anything still billing?).
#   bash infra/status.sh
# Anything flagged [$$$] is costing money right now: stop it with infra/teardown.sh.
set -uo pipefail
export AWS_DEFAULT_REGION=us-east-1
BILLING=0
ok()   { echo "  [ok]   $*"; }
miss() { echo "  [--]   $*"; }
cost() { echo "  [\$\$\$]  $*"; BILLING=$((BILLING + 1)); }

echo "== Identity"
aws sts get-caller-identity --query Arn --output text || { echo "AWS CLI not configured"; exit 1; }

echo "== EC2"
aws ec2 describe-instances --filters Name=tag:Name,Values=cs-kafka-ec2 \
  Name=instance-state-name,Values=pending,running,stopping,stopped \
  --query 'Reservations[].Instances[].[InstanceId,State.Name,InstanceType,PublicIpAddress]' --output text |
while read -r id state type ip; do
  case "$state" in
    running|pending) cost "$id $type $state  (ssh ec2-user@$ip)" ;;
    *)               ok   "$id $type $state  (only the 30 GB disk is billed)" ;;
  esac
done
[ -z "$(aws ec2 describe-instances --filters Name=tag:Name,Values=cs-kafka-ec2 \
  Name=instance-state-name,Values=pending,running,stopping,stopped \
  --query 'Reservations[].Instances[].InstanceId' --output text)" ] && miss "no cs-kafka-ec2 instance"

echo "== SageMaker"
NB=$(aws sagemaker describe-notebook-instance --notebook-instance-name cs-notebook \
     --query NotebookInstanceStatus --output text 2>/dev/null)
case "$NB" in
  "")                 miss "notebook cs-notebook not created" ;;
  InService|Pending)  cost "notebook cs-notebook $NB" ;;
  *)                  ok   "notebook cs-notebook $NB" ;;
esac
EPS=$(aws sagemaker list-endpoints --query 'Endpoints[].[EndpointName,EndpointStatus]' --output text)
if [ -z "$EPS" ]; then ok "no endpoints"
else echo "$EPS" | while read -r name status; do cost "endpoint $name $status"; done; fi

echo "== Glue"
TR=$(aws glue get-trigger --name cs-daily --query Trigger.State --output text 2>/dev/null)
[ -n "$TR" ] && ok "trigger cs-daily $TR (bills only while jobs run)" || miss "trigger cs-daily not created"
aws glue get-database --name cryptosentinel >/dev/null 2>&1 && ok "database cryptosentinel" \
  || miss "database cryptosentinel missing"

echo "== Storage / messaging (pay-per-use, near zero when idle)"
if [ -n "${BUCKET:-}" ]; then
  SIZE=$(aws s3 ls "s3://$BUCKET" --recursive --summarize 2>/dev/null | awk '/Total Size/ {print $3}')
  [ -n "$SIZE" ] && ok "s3://$BUCKET $(numfmt --to=iec "$SIZE" 2>/dev/null || echo "$SIZE bytes")" \
    || miss "s3://$BUCKET missing"
else miss "BUCKET not set: export BUCKET=... to check the bucket"; fi
for t in cs-live cs-news cs-alerts; do
  S=$(aws dynamodb describe-table --table-name "$t" --query Table.TableStatus --output text 2>/dev/null)
  [ -n "$S" ] && ok "dynamodb $t $S" || miss "dynamodb $t missing"
done
TOPIC=$(aws sns list-topics --query "Topics[?ends_with(TopicArn, ':cs-alerts')].TopicArn" --output text)
if [ -n "$TOPIC" ]; then
  ok "sns $TOPIC"
  aws sns list-subscriptions-by-topic --topic-arn "$TOPIC" \
    --query 'Subscriptions[].[Endpoint,SubscriptionArn]' --output text |
  while read -r ep arn; do
    [ "$arn" = "PendingConfirmation" ] && miss "$ep not confirmed: click the link in the e-mail" \
      || ok "$ep confirmed"
  done
else miss "sns topic cs-alerts missing"; fi

echo
if [ "$BILLING" -gt 0 ] || aws ec2 describe-instances --filters Name=tag:Name,Values=cs-kafka-ec2 \
     Name=instance-state-name,Values=pending,running --query 'Reservations[].Instances[].InstanceId' \
     --output text | grep -q .; then
  echo "Something is still running and billing: bash infra/teardown.sh"
else
  echo "Nothing billing by the hour. Safe to leave."
fi
