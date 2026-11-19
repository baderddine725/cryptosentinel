#!/bin/bash
# Create ALL the AWS resources CryptoSentinel needs, in one go. Safe to run again:
# anything that already exists is kept. Run from your laptop (WSL) with the AWS CLI
# configured with your Learner Lab credentials (AWS Details -> AWS CLI).
#
#   export BUCKET=cryptosentinel-bg-4821      # globally unique name
#   export EMAIL=you@example.com              # optional: alert e-mails
#   bash infra/bootstrap_aws.sh
#
# Console-only steps (no CLI possible): request Bedrock model access, and click the
# SNS confirmation link in your e-mail.
set -uo pipefail
: "${BUCKET:?set BUCKET first, e.g. export BUCKET=cryptosentinel-bg-4821}"
export AWS_DEFAULT_REGION=us-east-1
ok()   { echo "  [ok]   $*"; }
warn() { echo "  [warn] $*"; }

echo "== Identity"
aws sts get-caller-identity --query Arn --output text || { echo "AWS CLI not configured"; exit 1; }
ROLE_ARN=$(aws iam get-role --role-name LabRole --query Role.Arn --output text 2>/dev/null)
[ -n "$ROLE_ARN" ] && ok "LabRole: $ROLE_ARN" || warn "LabRole not found (not a Learner Lab account?)"

echo "== S3 bucket"
if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then ok "s3://$BUCKET exists"
else aws s3 mb "s3://$BUCKET" >/dev/null && ok "s3://$BUCKET created"; fi

echo "== DynamoDB tables"
make_table() {  # name, attribute definitions, key schema, ttl attribute (or "")
  if aws dynamodb describe-table --table-name "$1" >/dev/null 2>&1; then ok "$1 exists"; return; fi
  aws dynamodb create-table --table-name "$1" --billing-mode PAY_PER_REQUEST \
    --attribute-definitions $2 --key-schema $3 >/dev/null
  aws dynamodb wait table-exists --table-name "$1"
  [ -n "$4" ] && aws dynamodb update-time-to-live --table-name "$1" \
    --time-to-live-specification "Enabled=true,AttributeName=$4" >/dev/null
  ok "$1 created"
}
make_table cs-live   "AttributeName=symbol,AttributeType=S AttributeName=minute,AttributeType=N" \
                     "AttributeName=symbol,KeyType=HASH AttributeName=minute,KeyType=RANGE" expires
make_table cs-news   "AttributeName=coin,AttributeType=S AttributeName=ts_id,AttributeType=S" \
                     "AttributeName=coin,KeyType=HASH AttributeName=ts_id,KeyType=RANGE" expires
make_table cs-alerts "AttributeName=alert_id,AttributeType=S" "AttributeName=alert_id,KeyType=HASH" ""

echo "== SNS alert topic"
TOPIC=$(aws sns create-topic --name cs-alerts --query TopicArn --output text)  # idempotent
ok "$TOPIC"
if [ -n "${EMAIL:-}" ]; then
  if aws sns list-subscriptions-by-topic --topic-arn "$TOPIC" --query 'Subscriptions[].Endpoint' \
       --output text | grep -q "$EMAIL"; then ok "$EMAIL already subscribed"
  else aws sns subscribe --topic-arn "$TOPIC" --protocol email --notification-endpoint "$EMAIL" >/dev/null
       ok "subscription sent to $EMAIL -> click the confirmation link in the e-mail"; fi
fi

echo "== Glue database + Athena results folder"
if aws glue get-database --name cryptosentinel >/dev/null 2>&1; then ok "Glue database exists"
else aws glue create-database --database-input Name=cryptosentinel && ok "Glue database created"; fi
aws athena update-work-group --work-group primary --configuration-updates \
  "ResultConfigurationUpdates={OutputLocation=s3://$BUCKET/athena-results/}" 2>/dev/null \
  && ok "Athena results -> s3://$BUCKET/athena-results/" \
  || warn "set the Athena result location in the console (Athena -> Settings)"

echo "== Security group (SSH + Streamlit from your IP only)"
VPC=$(aws ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text)
SG=$(aws ec2 describe-security-groups --filters Name=group-name,Values=cs-sg Name=vpc-id,Values="$VPC" \
     --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null)
if [ "$SG" = "None" ] || [ -z "$SG" ]; then
  SG=$(aws ec2 create-security-group --group-name cs-sg --description "CryptoSentinel" \
       --vpc-id "$VPC" --query GroupId --output text); ok "cs-sg created ($SG)"
else ok "cs-sg exists ($SG)"; fi
# In the lab terminal, curl would return the LAB's IP, not your laptop's: export MYIP=x.x.x.x/32 first.
MYIP=${MYIP:-$(curl -s https://checkip.amazonaws.com)/32}
case "$MYIP" in */32) ;; *) MYIP="$MYIP/32" ;; esac
for port in 22 8501; do
  aws ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port $port \
    --cidr "$MYIP" >/dev/null 2>&1 && ok "port $port open to $MYIP" || ok "port $port rule already there"
done

echo "== EC2 instance"
IID=$(aws ec2 describe-instances --filters Name=tag:Name,Values=cs-kafka-ec2 \
      Name=instance-state-name,Values=pending,running,stopping,stopped \
      --query 'Reservations[0].Instances[0].InstanceId' --output text)
if [ "$IID" = "None" ] || [ -z "$IID" ]; then
  AMI=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
        --query Parameter.Value --output text)
  IID=$(aws ec2 run-instances --image-id "$AMI" --instance-type "${INSTANCE_TYPE:-t3.medium}" \
        --key-name vockey --security-group-ids "$SG" --iam-instance-profile Name=LabInstanceProfile \
        --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=30,VolumeType=gp3}' \
        --user-data file://"$(dirname "$0")"/user-data.sh \
        --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=cs-kafka-ec2},{Key=project,Value=cryptosentinel}]' \
        --query 'Instances[0].InstanceId' --output text)
  ok "instance $IID launched (Docker installs itself in ~2 min)"
else ok "instance $IID exists"; fi
aws ec2 start-instances --instance-ids "$IID" >/dev/null 2>&1
aws ec2 wait instance-running --instance-ids "$IID"
IP=$(aws ec2 describe-instances --instance-ids "$IID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

cat <<EOF

== Done. Put these lines in .env on the instance:
BUCKET=$BUCKET
SNS_TOPIC_ARN=$TOPIC

Connect:   ssh -i labsuser.pem ec2-user@$IP
Then:      git clone <your repo> cryptosentinel && cd cryptosentinel
           cp .env.aws.example .env && nano .env
           docker compose up -d --build && bash infra/create_topics.sh
Still to do in the console: Bedrock -> Model access (Nova Lite), and confirm the SNS e-mail.
EOF
