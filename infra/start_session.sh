#!/bin/bash
# Start of every AWS work session (from your laptop, after refreshing the lab credentials):
# starts the EC2 instance (the whole Docker stack starts with it) and prints how to connect.
#   bash infra/start_session.sh            # EC2 only
#   bash infra/start_session.sh --notebook # also start the SageMaker notebook (ML sessions)
set -uo pipefail
export AWS_DEFAULT_REGION=us-east-1
IID=$(aws ec2 describe-instances --filters Name=tag:Name,Values=cs-kafka-ec2 \
      Name=instance-state-name,Values=stopped,running,pending \
      --query 'Reservations[0].Instances[0].InstanceId' --output text)
[ "$IID" = "None" ] && { echo "No instance yet: run infra/bootstrap_aws.sh first"; exit 1; }
aws ec2 start-instances --instance-ids "$IID" >/dev/null
aws ec2 wait instance-running --instance-ids "$IID"
IP=$(aws ec2 describe-instances --instance-ids "$IID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
if [ "${1:-}" = "--notebook" ]; then
  aws sagemaker start-notebook-instance --notebook-instance-name cs-notebook 2>/dev/null \
    && echo "Notebook cs-notebook starting (~3 min)" || echo "Notebook not created yet (Phase 4)"
fi
echo "Instance $IID running.  ssh -i labsuser.pem ec2-user@$IP"
echo "Dashboard (later):      http://$IP:8501"
echo "Your IP may have changed since last time: if SSH times out, rerun infra/bootstrap_aws.sh"
echo "End of session:         bash infra/teardown.sh"
