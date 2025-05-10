#!/bin/bash
set -e

# -------- Configuration --------
AMI_ID="ami-0b8b44ec9a8f90422"        # Update based on your region
INSTANCE_TYPE="g5.xlarge"
KEY_NAME="harrison2025"
SECURITY_GROUP_ID="sg-xxxxxxxx"      # <-- update
SUBNET_ID="subnet-xxxxxxxx"          # <-- update
IAM_INSTANCE_PROFILE="EdgarEdgeTrainingInstanceProfile"  # <-- optional
SPOT_PRICE="0.20"
REGION="us-east-1"
TAG="edgar-edge-gpu-training"
INSTANCE_NAME="edgar-edge-gpu"

# -------- Launch Spot Request --------
echo ">>> Requesting spot instance: $INSTANCE_TYPE in $REGION"

SPOT_REQ_ID=$(aws ec2 request-spot-instances \
  --region "$REGION" \
  --spot-price "$SPOT_PRICE" \
  --instance-count 1 \
  --type "one-time" \
  --launch-specification "{
      \"ImageId\": \"$AMI_ID\",
      \"InstanceType\": \"$INSTANCE_TYPE\",
      \"KeyName\": \"$KEY_NAME\",
      \"SubnetId\": \"$SUBNET_ID\",
      \"SecurityGroupIds\": [\"$SECURITY_GROUP_ID\"],
      \"IamInstanceProfile\": {\"Name\": \"$IAM_INSTANCE_PROFILE\"},
      \"BlockDeviceMappings\": [
        {
          \"DeviceName\": \"/dev/sda1\",
          \"Ebs\": {
            \"VolumeSize\": 100,
            \"VolumeType\": \"gp3\"
          }
        }
      ]
    }" \
  --query 'SpotInstanceRequests[0].SpotInstanceRequestId' \
  --output text)

echo "✅ Spot request submitted: $SPOT_REQ_ID"
echo "⌛ Waiting for fulfillment..."

# -------- Wait for Fulfillment --------
INSTANCE_ID=""
for i in {1..30}; do
  INSTANCE_ID=$(aws ec2 describe-spot-instance-requests \
    --region "$REGION" \
    --spot-instance-request-ids "$SPOT_REQ_ID" \
    --query 'SpotInstanceRequests[0].InstanceId' \
    --output text)
  
  if [[ "$INSTANCE_ID" != "None" ]]; then
    break
  fi
  
  echo "Waiting for instance assignment..."
  sleep 10
done

if [[ "$INSTANCE_ID" == "None" || -z "$INSTANCE_ID" ]]; then
  echo "❌ Instance request not fulfilled in time."
  exit 1
fi

# -------- Add Tags --------
echo "🏷️  Tagging instance $INSTANCE_ID..."
aws ec2 create-tags \
  --region "$REGION" \
  --resources "$INSTANCE_ID" \
  --tags "Key=Name,Value=$INSTANCE_NAME" "Key=Project,Value=$TAG"

# -------- Get Public IP --------
PUBLIC_IP=$(aws ec2 describe-instances \
  --region "$REGION" \
  --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)

echo "✅ Spot instance is ready: $INSTANCE_ID"
echo "🌐 Public IP: $PUBLIC_IP"
echo "🔐 SSH command:"
echo "    ssh -i ~/.ssh/${KEY_NAME}.pem ubuntu@${PUBLIC_IP}"
