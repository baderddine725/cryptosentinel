#!/bin/bash
# AWS only. Run at the end of EVERY session from your laptop (AWS CLI with lab credentials).
# Add --final on the last day to remove the serverless endpoints and the Glue trigger too.
set -u
IID=$(aws ec2 describe-instances --filters Name=tag:Name,Values=cs-kafka-ec2 \
      Name=instance-state-name,Values=running --query 'Reservations[].Instances[].InstanceId' --output text)
[ -n "$IID" ] && aws ec2 stop-instances --instance-ids $IID
aws sagemaker stop-notebook-instance --notebook-instance-name cs-notebook 2>/dev/null
aws sagemaker delete-endpoint --endpoint-name cs-rcf-rt 2>/dev/null
if [ "${1:-}" = "--final" ]; then
  for e in cs-rcf cs-xgb; do aws sagemaker delete-endpoint --endpoint-name $e 2>/dev/null; done
  aws glue delete-trigger --name cs-daily 2>/dev/null
fi
echo "Done. Check the remaining budget in the Learner Lab panel."
